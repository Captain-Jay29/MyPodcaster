"""Fixtures for evaluation tests.

Provides pre-scraped articles and an instrumented agent run for eval metrics.
"""

import asyncio
import time
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch

import pytest

from app.models import BriefingScript, Job

# ──────────────────────────────────────────────
# Fixture articles (pre-scraped content)
# ──────────────────────────────────────────────

EVAL_ARTICLES = [
    {
        "hn_id": "sample1",
        "title": "Show HN: I built a database in Rust that's 10x faster than SQLite",
        "url": "https://example.com/rust-db",
        "content": (
            "RustDB is a new embedded database written entirely in Rust. "
            "In benchmarks, it achieves 10x the throughput of SQLite for write-heavy workloads, "
            "processing 1.2 million writes per second on commodity hardware. "
            "The project is open-sourced under the MIT license and supports ACID transactions. "
            "It uses a log-structured merge tree (LSM) storage engine with a custom write-ahead log. "
            "The author, a former Google engineer, spent two years building it as a side project. "
            "Early adopters report significant performance gains in IoT and time-series use cases."
        ),
        "points": 342,
        "num_comments": 128,
        "expected_key_points": [
            "New database written in Rust",
            "10x throughput vs SQLite for writes",
            "Open-sourced under MIT license",
        ],
    },
    {
        "hn_id": "sample2",
        "title": "OpenAI publishes new framework for evaluating frontier AI risks",
        "url": "https://example.com/openai-safety",
        "content": (
            "OpenAI has released a new Preparedness Framework for systematically evaluating "
            "risks from frontier AI models before deployment. The framework categorizes risks "
            "into four levels: low, medium, high, and critical, across dimensions including "
            "cybersecurity, biological threats, persuasion, and model autonomy. Models scoring "
            "high or critical on any dimension cannot be deployed. The framework requires "
            "independent review by a safety advisory group before launch decisions. "
            "Critics argue the thresholds are too vague and self-assessed. OpenAI says "
            "the framework will be updated quarterly based on new research."
        ),
        "points": 289,
        "num_comments": 201,
        "expected_key_points": [
            "New risk evaluation framework from OpenAI",
            "Four risk levels across multiple dimensions",
            "Independent safety review required before deployment",
        ],
    },
    {
        "hn_id": "sample3",
        "title": "Why Zig might be the next systems language after Rust",
        "url": "https://example.com/zig-systems",
        "content": (
            "A detailed analysis of Zig's growing adoption in systems programming. "
            "Unlike Rust, Zig opts for simplicity over safety guarantees, with no hidden "
            "control flow, no operator overloading, and no garbage collector. "
            "The language has gained traction after being adopted by Uber for their "
            "real-time compute platform, replacing C++ components. Zig's comptime "
            "feature enables compile-time code execution that eliminates entire categories "
            "of runtime overhead. The Zig Software Foundation reports a 300 percent increase "
            "in corporate sponsors over the past year. However, the ecosystem remains small "
            "with fewer than 2000 packages on the main package registry."
        ),
        "points": 215,
        "num_comments": 167,
        "expected_key_points": [
            "Zig gaining adoption in systems programming",
            "Adopted by Uber for real-time compute",
            "Simpler than Rust but fewer safety guarantees",
        ],
    },
    {
        "hn_id": "sample4",
        "title": "Critical RCE vulnerability found in popular npm package with 40M weekly downloads",
        "url": "https://example.com/npm-vuln",
        "content": (
            "Security researchers at Snyk have disclosed a critical remote code execution "
            "vulnerability in json-parser-lite, an npm package downloaded over 40 million "
            "times per week. The vulnerability, tracked as CVE-2026-1234, allows attackers "
            "to execute arbitrary code by sending specially crafted JSON payloads. The flaw "
            "exists in the package's streaming parser mode and affects versions 2.0 through "
            "2.4.1. A patched version 2.4.2 has been released. Major frameworks including "
            "Express and Fastify have issued advisories urging immediate updates. The "
            "vulnerability was responsibly disclosed 90 days ago."
        ),
        "points": 478,
        "num_comments": 234,
        "expected_key_points": [
            "Critical RCE in json-parser-lite npm package",
            "40 million weekly downloads affected",
            "Patched version available, frameworks issuing advisories",
        ],
    },
    {
        "hn_id": "sample5",
        "title": "Linux kernel 7.0 released with major performance improvements",
        "url": "https://example.com/linux-7",
        "content": (
            "Linus Torvalds has announced the release of Linux kernel 7.0, marking "
            "a major milestone in the project's 35-year history. Key improvements include "
            "a redesigned I/O scheduler that improves NVMe throughput by 40 percent, "
            "native support for the Rust programming language in driver development, "
            "and a new memory management subsystem that reduces page fault latency by 25 percent. "
            "The release also includes initial support for RISC-V server workloads. "
            "Torvalds noted that despite the major version bump, the release process was "
            "unusually smooth with fewer regression reports than typical point releases."
        ),
        "points": 512,
        "num_comments": 189,
        "expected_key_points": [
            "Linux kernel 7.0 released",
            "40 percent NVMe throughput improvement",
            "Native Rust support for drivers",
        ],
    },
]


# ──────────────────────────────────────────────
# Agent trace dataclasses
# ──────────────────────────────────────────────


@dataclass
class TurnTrace:
    turn_num: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cumulative_tokens: int
    latency_ms: float
    tool_call_count: int


@dataclass
class ToolCallTrace:
    name: str
    args: dict
    latency_ms: float
    result_chars: int


@dataclass
class AgentTrace:
    script: BriefingScript | None = None
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    turns: list[TurnTrace] = field(default_factory=list)
    wall_clock_s: float = 0.0
    total_tokens: int = 0


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def eval_articles():
    return EVAL_ARTICLES


def _build_search_results(articles: list[dict]) -> str:
    """Format fixture articles as search_hn output."""
    lines = []
    for i, a in enumerate(articles):
        lines.append(
            f"{i + 1}. [{a['points']} pts, {a.get('num_comments', 0)} comments] {a['title']}\n"
            f"   URL: {a['url']}\n"
            f"   HN ID: {a['hn_id']} | Date: 2026-02-19"
        )
    return f"Found {len(articles)} articles:\n\n" + "\n\n".join(lines)


def _content_by_url() -> dict[str, str]:
    """Map URL -> content for mocking read_url."""
    return {a["url"]: a["content"] for a in EVAL_ARTICLES}


@pytest.fixture(scope="session")
def agent_trace():
    """Run the real agent with mocked tools. Session-scoped so it runs once."""
    from app.agent import run_agent

    trace = AgentTrace()
    content_map = _content_by_url()
    search_result = _build_search_results(EVAL_ARTICLES)

    # Track tool calls
    tool_call_log: list[ToolCallTrace] = []

    async def mock_search_hn(query: str = "", sort: str = "points", limit: int | None = None):
        start = time.perf_counter()
        await asyncio.sleep(0.01)  # simulate minimal latency
        result = search_result
        elapsed_ms = (time.perf_counter() - start) * 1000
        tool_call_log.append(ToolCallTrace(
            name="search_hn",
            args={"query": query, "sort": sort, "limit": limit},
            latency_ms=elapsed_ms,
            result_chars=len(result),
        ))
        return result, None

    async def mock_read_url(url: str):
        start = time.perf_counter()
        await asyncio.sleep(0.01)
        content = content_map.get(url, f"[ERROR] URL not found in fixtures: {url}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        tool_call_log.append(ToolCallTrace(
            name="read_url",
            args={"url": url},
            latency_ms=elapsed_ms,
            result_chars=len(content),
        ))
        return content, None

    # Wrap the OpenAI create call to capture per-turn token data
    turn_log: list[TurnTrace] = []
    cumulative_tokens = 0

    async def run_instrumented():
        nonlocal cumulative_tokens

        from app.agent import get_openai_client

        real_client = get_openai_client()
        original_create = real_client.chat.completions.create
        turn_counter = 0

        async def instrumented_create(*args, **kwargs):
            nonlocal turn_counter, cumulative_tokens
            turn_counter += 1
            turn_num = turn_counter

            start = time.perf_counter()
            response = await original_create(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            usage = response.usage
            prompt_tokens = usage.prompt_tokens if usage else 0
            completion_tokens = usage.completion_tokens if usage else 0
            total = usage.total_tokens if usage else 0
            cumulative_tokens += total

            tool_call_count = 0
            if response.choices and response.choices[0].message.tool_calls:
                tool_call_count = len(response.choices[0].message.tool_calls)

            turn_log.append(TurnTrace(
                turn_num=turn_num,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
                cumulative_tokens=cumulative_tokens,
                latency_ms=elapsed_ms,
                tool_call_count=tool_call_count,
            ))

            return response

        real_client.chat.completions.create = instrumented_create  # type: ignore[assignment]

        try:
            job = Job(job_id="eval-session")
            with (
                patch("app.agent.search_hn", side_effect=mock_search_hn),
                patch("app.agent.read_url", side_effect=mock_read_url),
            ):
                script = await run_agent(
                    interests="rust, AI safety, security, linux",
                    num_articles=5,
                    job=job,
                )
            return script
        finally:
            real_client.chat.completions.create = original_create  # type: ignore[assignment]

    wall_start = time.perf_counter()
    loop = asyncio.new_event_loop()
    try:
        script = loop.run_until_complete(run_instrumented())
    finally:
        loop.close()
    wall_s = time.perf_counter() - wall_start

    trace.script = script
    trace.tool_calls = tool_call_log
    trace.turns = turn_log
    trace.wall_clock_s = wall_s
    trace.total_tokens = cumulative_tokens

    return trace


@pytest.fixture
def article_pairs(agent_trace):
    """Zip each generated ArticleSummary with its source content."""
    content_map = _content_by_url()
    pairs = []
    for article in agent_trace.script.articles:
        source = content_map.get(article.url, "")
        if source:
            pairs.append((article, source))
    return pairs
