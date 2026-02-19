"""
LLM agent with tool-use loop.
Searches HN, reads articles, produces a BriefingScript.
"""

import asyncio
import json
from datetime import datetime

from loguru import logger
from openai import AsyncOpenAI

from app.config import settings
from app.models import (
    BriefingError,
    BriefingScript,
    ErrorSeverity,
    Job,
)
from app.tools import TOOL_DEFINITIONS, read_url, search_hn

# ──────────────────────────────────────────────
# OpenAI Client (singleton)
# ──────────────────────────────────────────────

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Return a shared AsyncOpenAI client, creating it on first use."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


# ──────────────────────────────────────────────
# System Prompt
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an audio briefing producer. Your job is to research Hacker News articles \
and write self-contained audio summaries for each one.

## Your tools
- search_hn(query?, sort?, limit?): Search Hacker News via Algolia. \
  No query = today's top stories. With query = topic search.
- read_url(url): Read the full content of any URL. Returns clean text.

## Your process
1. SEARCH: Call search_hn to find candidate articles. If the user provided interests, \
   search for those topics (try 2-3 related search terms). If no interests, fetch top stories.
2. EVALUATE: From the search results, mentally select the most newsworthy, diverse, and \
   substantive articles. Skip: job postings, Show HN with <10 points, duplicates on the same topic.
3. READ: Call read_url on each selected article's URL to get the full content. \
   You can call read_url multiple times in parallel. If read_url fails or returns \
   thin content, you'll still include the article but with a shorter mention based on the title.
4. WRITE: After reading articles, produce your final output as valid JSON matching \
   the BriefingScript schema below.

## Summary format rules
- Each article gets a SELF-CONTAINED summary of 60-80 words (~30 seconds spoken).
- The listener may play articles in any order or skip some — do NOT reference other articles.
- Write for the EAR, not the eye:
  - No markdown, no bullet points, no URLs, no parentheses.
  - Short sentences (under 20 words each).
  - Natural spoken English, as if briefing a colleague.
- Structure each summary as: What happened. Why it matters. What to watch for.
- Be direct and specific. No filler like "In this article, the author discusses..."

## Accuracy rules
- Do NOT invent facts, numbers, names, or claims not in the source.
- If you could not read an article, say only what you know from the title and HN metadata.
- If uncertain about a detail, omit it rather than guess.

## Output format
When you have gathered enough information, respond with ONLY a JSON object (no markdown \
code fences, no extra text) matching this schema:

{
  "articles": [
    {
      "title": "Original article title from HN",
      "url": "https://...",
      "hn_id": "12345",
      "points": 342,
      "num_comments": 128,
      "summary_text": "Your 60-80 word spoken summary here."
    }
  ]
}
"""


def build_user_message(interests: str, num_articles: int) -> str:
    """Build the initial user message with today's date and interests."""
    today = datetime.now().strftime("%A, %B %d, %Y")
    if interests.strip():
        return (
            f"Today is {today}. The listener is interested in: {interests}. "
            f"Search for articles on these topics — try a few related search terms. "
            f"Also check top stories in case something major happened. "
            f"Select and summarize the {num_articles} most relevant articles."
        )
    return (
        f"Today is {today}. No specific interests provided. "
        f"Fetch today's top stories and select the {num_articles} most "
        f"newsworthy, diverse articles. Summarize each one."
    )


# ──────────────────────────────────────────────
# Tool Dispatch
# ──────────────────────────────────────────────


async def execute_tool(
    tool_name: str,
    arguments: dict,
    job: Job,
    errors: list[BriefingError],
) -> str:
    """Execute a tool call and return the result string."""
    if tool_name == "search_hn":
        query = arguments.get("query", "")
        sort = arguments.get("sort", "points")
        limit = arguments.get("limit", 20)

        logger.info(
            "[{}] search_hn(query={!r}, sort={!r}, limit={})", job.job_id, query, sort, limit
        )
        job.progress.message = (
            f"Searching HN for '{query}'..." if query else "Fetching top stories..."
        )

        result, error = await search_hn(query=query, sort=sort, limit=limit)
        if error:
            errors.append(error)
        else:
            # Count articles found (rough parse)
            job.progress.articles_found = result.count(". [")

        return result

    if tool_name == "read_url":
        url = arguments.get("url", "")

        logger.info("[{}] read_url(url={!r})", job.job_id, url[:80])
        job.progress.articles_read += 1
        job.progress.message = f"Reading article {job.progress.articles_read}..."

        result, error = await read_url(url=url)
        if error:
            errors.append(error)

        return result

    return f"[ERROR] Unknown tool: {tool_name}"


# ──────────────────────────────────────────────
# Agent Loop
# ──────────────────────────────────────────────


async def _agent_loop(
    interests: str,
    num_articles: int,
    job: Job,
    errors: list[BriefingError],
) -> BriefingScript:
    """Core agent loop. Raises on unrecoverable failure."""
    client = get_openai_client()

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(interests, num_articles)},
    ]

    total_tokens = 0

    for turn in range(settings.agent_max_turns):
        logger.debug("[{}] Agent turn {}/{}", job.job_id, turn + 1, settings.agent_max_turns)

        # Check token budget — force text-only response if exceeded
        budget_exceeded = total_tokens > settings.agent_max_tokens
        if budget_exceeded:
            logger.warning(
                "[{}] Token budget exceeded ({}). Forcing finalization.", job.job_id, total_tokens
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "You have used your research budget. Produce your final JSON output NOW "
                        "using whatever articles you have gathered so far."
                    ),
                }
            )

        # Call LLM
        response = await client.chat.completions.create(  # type: ignore[call-overload]
            model=settings.openai_model,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="none" if budget_exceeded else "auto",
        )

        total_tokens += response.usage.total_tokens if response.usage else 0
        choice = response.choices[0]

        # ── Tool calls ──
        if choice.message.tool_calls:
            messages.append(choice.message)  # type: ignore[arg-type]

            # Gather tool call info
            tool_tasks = [
                (tc.id, tc.function.name, json.loads(tc.function.arguments))
                for tc in choice.message.tool_calls
            ]

            # Run all tool calls concurrently
            results = await asyncio.gather(
                *[execute_tool(name, args, job, errors) for _, name, args in tool_tasks]
            )

            for (tc_id, _, _), result in zip(tool_tasks, results, strict=False):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result,
                    }
                )

            continue

        # ── Final response (no tool calls) ──
        if choice.finish_reason == "stop" and choice.message.content:
            content = choice.message.content.strip()

            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            script = BriefingScript.model_validate_json(content)
            logger.info(
                "[{}] Agent produced {} articles in {} turns, {} tokens",
                job.job_id,
                len(script.articles),
                turn + 1,
                total_tokens,
            )
            return script

    # Exhausted all turns
    raise AgentTimeoutError(f"Agent did not produce output within {settings.agent_max_turns} turns")


async def run_agent(interests: str, num_articles: int, job: Job) -> BriefingScript:
    """
    Top-level agent entry point. Wraps _agent_loop with timeout.
    Attaches errors to job even on success.
    """
    errors: list[BriefingError] = []

    try:
        script = await asyncio.wait_for(
            _agent_loop(interests, num_articles, job, errors),
            timeout=settings.agent_timeout_seconds,
        )
        job.errors.extend(errors)
        return script

    except TimeoutError:
        error = BriefingError(
            code="agent_timeout",
            message=(
                f"Agent did not finish within {settings.agent_timeout_seconds}s. "
                f"Read {job.progress.articles_read} articles before timeout."
            ),
            severity=ErrorSeverity.FATAL,
            source="agent",
            context={
                "articles_read": job.progress.articles_read,
                "timeout_seconds": settings.agent_timeout_seconds,
            },
        )
        job.errors.extend([*errors, error])
        raise

    except json.JSONDecodeError as e:
        error = BriefingError(
            code="agent_bad_output",
            message=f"Agent output was not valid JSON: {e!s}"[:200],
            severity=ErrorSeverity.FATAL,
            source="agent",
            context={"parse_error": str(e)},
        )
        job.errors.extend([*errors, error])
        raise

    except Exception as e:
        error = BriefingError(
            code="agent_error",
            message=f"Agent failed: {type(e).__name__}: {e!s}",
            severity=ErrorSeverity.FATAL,
            source="agent",
            context={"exception_type": type(e).__name__},
        )
        job.errors.extend([*errors, error])
        raise


# ──────────────────────────────────────────────
# Custom Exceptions
# ──────────────────────────────────────────────


class AgentTimeoutError(Exception):
    pass
