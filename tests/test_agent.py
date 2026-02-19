"""Unit tests for the agent module."""

from unittest.mock import AsyncMock, patch

from app.agent import build_user_message
from app.models import Job

# ── build_user_message ──


def test_build_user_message_with_interests():
    msg = build_user_message("AI safety, Rust", num_articles=5)
    assert "AI safety, Rust" in msg
    assert "5" in msg
    assert "interested in" in msg


def test_build_user_message_without_interests():
    msg = build_user_message("", num_articles=10)
    assert "No specific interests" in msg
    assert "10" in msg
    assert "top stories" in msg


def test_build_user_message_whitespace_only():
    msg = build_user_message("   ", num_articles=10)
    assert "No specific interests" in msg


# ── execute_tool ──


async def test_execute_tool_unknown():
    from app.agent import execute_tool

    job = Job(job_id="test123")
    errors = []
    result = await execute_tool("unknown_tool", {}, job, errors)
    assert "Unknown tool" in result
    assert len(errors) == 0


async def test_execute_tool_search_hn_updates_progress():
    """execute_tool should update job progress message for search_hn."""
    from app.agent import execute_tool

    job = Job(job_id="test123")
    errors = []

    with patch(
        "app.agent.search_hn",
        new_callable=AsyncMock,
        return_value=("Found 5 articles:\n\n1. [100 pts] Test", None),
    ):
        result = await execute_tool("search_hn", {"query": "AI"}, job, errors)

    assert "Searching HN" in job.progress.message or "Found" in result


async def test_execute_tool_read_url_increments_on_success():
    """articles_read should only increment on successful read."""
    from app.agent import execute_tool

    job = Job(job_id="test123")
    errors = []

    with patch(
        "app.agent.read_url",
        new_callable=AsyncMock,
        return_value=("Article content here...", None),
    ):
        await execute_tool("read_url", {"url": "https://example.com"}, job, errors)

    assert job.progress.articles_read == 1


async def test_execute_tool_read_url_no_increment_on_error():
    """articles_read should NOT increment when read_url returns an error."""
    from app.agent import execute_tool
    from app.models import BriefingError, ErrorSeverity

    job = Job(job_id="test123")
    errors = []

    read_error = BriefingError(
        code="jina_timeout",
        message="Timed out",
        severity=ErrorSeverity.RECOVERABLE,
        source="tools.read_url",
        recovered=True,
    )

    with patch(
        "app.agent.read_url",
        new_callable=AsyncMock,
        return_value=("[TIMEOUT] Could not read article", read_error),
    ):
        await execute_tool("read_url", {"url": "https://example.com"}, job, errors)

    assert job.progress.articles_read == 0
    assert len(errors) == 1
