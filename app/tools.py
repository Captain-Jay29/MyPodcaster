"""
Agent tools: search_hn() and read_url().
Both return strings (never raise to the agent).
Both return (content_string, optional_error) tuples internally.
"""

from datetime import UTC, datetime, timedelta

import httpx
from cachetools import TTLCache

from app.config import settings
from app.models import BriefingError, ErrorSeverity

# ──────────────────────────────────────────────
# Caches
# ──────────────────────────────────────────────

_hn_cache: TTLCache = TTLCache(maxsize=100, ttl=300)  # 5 min
_url_cache: TTLCache = TTLCache(maxsize=200, ttl=3600)  # 1 hour


# ──────────────────────────────────────────────
# Tool: search_hn
# ──────────────────────────────────────────────

ALGOLIA_BASE = "https://hn.algolia.com/api/v1"


async def search_hn(
    query: str = "",
    sort: str = "points",
    limit: int = 20,
) -> tuple[str, BriefingError | None]:
    """
    Search Hacker News via Algolia API.
    Returns (formatted_results_string, optional_error).
    """
    cache_key = f"{query}|{sort}|{limit}"
    if cache_key in _hn_cache:
        return _hn_cache[cache_key], None

    try:
        # Build Algolia URL
        params: dict = {"tags": "story", "hitsPerPage": min(limit, 30)}

        if query.strip():
            endpoint = "search" if sort == "relevance" else "search_by_date"
            params["query"] = query
        else:
            # No query = recent top stories
            endpoint = "search"
            # Filter to last 24h
            yesterday = int((datetime.now(UTC) - timedelta(days=1)).timestamp())
            params["numericFilters"] = f"created_at_i>{yesterday}"

        url = f"{ALGOLIA_BASE}/{endpoint}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        hits = data.get("hits", [])
        if not hits:
            msg = (
                f"[NO RESULTS] No HN articles found for query '{query}'. "
                f"Try a broader search term, or call search_hn with no query to get top stories."
            )
            return msg, BriefingError(
                code="hn_no_results",
                message=f"No results for '{query}'",
                severity=ErrorSeverity.RECOVERABLE,
                source="tools.search_hn",
                context={"query": query},
                recovered=True,
                recovery_action="Agent will retry with broader query or use top stories",
            )

        # Sort by points if requested (Algolia returns by relevance/date)
        if sort == "points":
            hits.sort(key=lambda h: h.get("points", 0) or 0, reverse=True)

        # Format for agent consumption
        lines = []
        for i, hit in enumerate(hits[:limit]):
            title = hit.get("title", "Untitled")
            url_val = hit.get("url", "")
            points = hit.get("points", 0) or 0
            comments = hit.get("num_comments", 0) or 0
            hn_id = hit.get("objectID", "")
            created = hit.get("created_at", "")[:10]  # just the date

            lines.append(
                f"{i + 1}. [{points} pts, {comments} comments] {title}\n"
                f"   URL: {url_val}\n"
                f"   HN ID: {hn_id} | Date: {created}"
            )

        result = f"Found {len(hits)} articles:\n\n" + "\n\n".join(lines)
        _hn_cache[cache_key] = result
        return result, None

    except httpx.TimeoutException:
        error = BriefingError(
            code="hn_timeout",
            message="Algolia HN search timed out after 10s",
            severity=ErrorSeverity.RECOVERABLE,
            source="tools.search_hn",
            context={"query": query, "timeout_seconds": 10},
            recovered=True,
            recovery_action="Agent should retry or try a different query",
        )
        return "[TIMEOUT] HN search timed out. Try again or use a different query.", error

    except httpx.HTTPStatusError as e:
        error = BriefingError(
            code="hn_http_error",
            message=f"Algolia returned HTTP {e.response.status_code}",
            severity=ErrorSeverity.RECOVERABLE,
            source="tools.search_hn",
            context={"query": query, "status_code": e.response.status_code},
            recovered=True,
            recovery_action="Agent should retry",
        )
        return f"[ERROR] HN search failed with HTTP {e.response.status_code}. Try again.", error

    except Exception as e:
        error = BriefingError(
            code="hn_unknown_error",
            message=f"Unexpected error searching HN: {type(e).__name__}: {e!s}",
            severity=ErrorSeverity.RECOVERABLE,
            source="tools.search_hn",
            context={"query": query, "exception_type": type(e).__name__},
            recovered=True,
            recovery_action="Agent should try a different approach",
        )
        return f"[ERROR] Unexpected failure searching HN: {e!s}", error


# ──────────────────────────────────────────────
# Tool: read_url
# ──────────────────────────────────────────────

JINA_READER_PREFIX = "https://r.jina.ai/"


async def read_url(url: str) -> tuple[str, BriefingError | None]:
    """
    Read article content via Jina Reader API.
    Returns (content_string, optional_error).
    """
    if url in _url_cache:
        return _url_cache[url], None

    try:
        headers = {
            "Accept": "text/markdown",
            "X-Return-Format": "markdown",
        }
        if settings.jina_api_key:
            headers["Authorization"] = f"Bearer {settings.jina_api_key}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{JINA_READER_PREFIX}{url}", headers=headers)
            resp.raise_for_status()

        content = resp.text.strip()

        if len(content) < 100:
            error = BriefingError(
                code="jina_thin_content",
                message=f"Article at {url} returned only {len(content)} chars",
                severity=ErrorSeverity.RECOVERABLE,
                source="tools.read_url",
                context={"url": url, "content_length": len(content)},
                recovered=True,
                recovery_action="Agent will use available text plus title for brief mention",
            )
            return (
                f"[THIN CONTENT] Only {len(content)} chars extracted from {url}.\n"
                f"Content: {content[:500]}\n"
                f"Use this plus the article title for a brief summary.",
                error,
            )

        # Truncate to manage token budget
        truncated = content[: settings.max_article_content_length]
        _url_cache[url] = truncated
        return truncated, None

    except httpx.TimeoutException:
        error = BriefingError(
            code="jina_timeout",
            message=f"Timed out reading {url} after 15s",
            severity=ErrorSeverity.RECOVERABLE,
            source="tools.read_url",
            context={"url": url, "timeout_seconds": 15},
            recovered=True,
            recovery_action="Agent will write brief mention from title only",
        )
        return (
            f"[TIMEOUT] Could not read {url} within 15 seconds. "
            f"Write a brief mention using the article title and HN metadata only.",
            error,
        )

    except httpx.HTTPStatusError as e:
        code_map = {
            403: ("jina_forbidden", "Access denied (likely paywall or bot protection)"),
            429: ("jina_rate_limited", "Rate limited by Jina API"),
            500: ("jina_server_error", "Jina Reader internal error"),
        }
        err_code, err_msg = code_map.get(
            e.response.status_code,
            ("jina_http_error", f"HTTP {e.response.status_code}"),
        )
        error = BriefingError(
            code=err_code,
            message=f"{err_msg} for {url}",
            severity=ErrorSeverity.RECOVERABLE,
            source="tools.read_url",
            context={"url": url, "status_code": e.response.status_code},
            recovered=True,
            recovery_action="Agent will write brief mention from title only",
        )
        return (
            f"[{err_code.upper()}] Could not read {url}: {err_msg}. "
            f"Write a brief mention using the article title and HN metadata only.",
            error,
        )

    except Exception as e:
        error = BriefingError(
            code="jina_unknown_error",
            message=f"Unexpected error reading {url}: {type(e).__name__}: {e!s}",
            severity=ErrorSeverity.RECOVERABLE,
            source="tools.read_url",
            context={"url": url, "exception_type": type(e).__name__},
            recovered=True,
            recovery_action="Agent will write brief mention from title only",
        )
        return (
            f"[ERROR] Unexpected failure reading {url}. "
            f"Write a brief mention using the article title and HN metadata only.",
            error,
        )


# ──────────────────────────────────────────────
# OpenAI Tool Definitions (for function calling)
# ──────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_hn",
            "description": (
                "Search Hacker News articles via Algolia. "
                "Returns titles, URLs, points, and comment counts. "
                "Call with no query to browse today's top stories. "
                "Call with a query to find topic-specific articles. "
                "You can call this multiple times with different queries to expand your search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms. Empty or omit for top stories.",
                    },
                    "sort": {
                        "type": "string",
                        "enum": ["relevance", "date", "points"],
                        "description": "Sort order. Default: points.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results (1-30). Default: 20.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": (
                "Fetch and read the full content of any URL. "
                "Returns clean text/markdown of the page. "
                "Use to read article content before summarizing. "
                "If it fails, you'll get an error message — "
                "use the article title for a brief mention instead. "
                "You can call this on multiple URLs in parallel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to read.",
                    },
                },
                "required": ["url"],
            },
        },
    },
]
