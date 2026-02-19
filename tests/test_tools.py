"""Integration tests for agent tools (hit real APIs)."""

import pytest

from app.tools import read_url, search_hn


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_hn_returns_results():
    """Algolia should return results for common queries."""
    result, error = await search_hn(query="python", limit=3)
    assert "pts" in result
    assert error is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_hn_empty_query():
    """Top stories mode should return results."""
    result, error = await search_hn(query="", limit=3)
    assert "Found" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_url_success():
    """Should read a known accessible URL."""
    result, error = await read_url("https://example.com")
    assert len(result) > 50
    assert error is None
