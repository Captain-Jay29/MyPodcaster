"""Tests for agent tools (search_hn, read_url)."""

from unittest.mock import MagicMock

import httpx
import pytest

from app.tools import read_url, search_hn

# ──────────────────────────────────────────────
# Unit tests (mocked httpx)
# ──────────────────────────────────────────────


def _mock_response(json_data=None, text="", status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
    return resp


async def test_search_hn_formats_results(mock_httpx):
    """search_hn should format Algolia hits into readable text."""
    mock_httpx.get.return_value = _mock_response(
        json_data={
            "hits": [
                {
                    "title": "Test Article",
                    "url": "https://example.com/test",
                    "points": 150,
                    "num_comments": 42,
                    "objectID": "99999",
                    "created_at": "2026-02-19T00:00:00Z",
                }
            ]
        }
    )

    result, error = await search_hn(query="unique_test_query_abc", limit=5)

    assert error is None
    assert "Test Article" in result
    assert "150 pts" in result
    assert "42 comments" in result
    assert "99999" in result


async def test_search_hn_no_results(mock_httpx):
    """search_hn should return a helpful message when no hits."""
    mock_httpx.get.return_value = _mock_response(json_data={"hits": []})

    result, error = await search_hn(query="unique_no_results_xyz")

    assert "NO RESULTS" in result
    assert error is not None
    assert error.code == "hn_no_results"
    assert error.recovered is True


async def test_search_hn_timeout(mock_httpx):
    """search_hn should handle timeout gracefully."""
    mock_httpx.get.side_effect = httpx.TimeoutException("timed out")

    result, error = await search_hn(query="unique_timeout_query")

    assert "TIMEOUT" in result
    assert error is not None
    assert error.code == "hn_timeout"


async def test_search_hn_http_error(mock_httpx):
    """search_hn should handle HTTP errors."""
    mock_httpx.get.return_value = _mock_response(status_code=500)

    result, error = await search_hn(query="unique_http_error_query")

    assert "ERROR" in result
    assert error is not None
    assert error.code == "hn_http_error"


async def test_read_url_success(mock_httpx):
    """read_url should return truncated content."""
    long_content = "A" * 5000
    mock_httpx.get.return_value = _mock_response(text=long_content)

    result, error = await read_url("https://unique-test-url-success.example.com")

    assert error is None
    assert len(result) == 2000  # truncated to max_article_content_length


async def test_read_url_thin_content(mock_httpx):
    """read_url should flag thin content."""
    mock_httpx.get.return_value = _mock_response(text="Short.")

    result, error = await read_url("https://unique-test-url-thin.example.com")

    assert "THIN CONTENT" in result
    assert error is not None
    assert error.code == "jina_thin_content"


async def test_read_url_timeout(mock_httpx):
    """read_url should handle timeout gracefully."""
    mock_httpx.get.side_effect = httpx.TimeoutException("timed out")

    result, error = await read_url("https://unique-test-url-timeout.example.com")

    assert "TIMEOUT" in result
    assert error is not None
    assert error.code == "jina_timeout"


async def test_read_url_forbidden(mock_httpx):
    """read_url should handle 403 with specific error code."""
    mock_httpx.get.return_value = _mock_response(status_code=403)

    result, error = await read_url("https://unique-test-url-403.example.com")

    assert error is not None
    assert error.code == "jina_forbidden"


# ──────────────────────────────────────────────
# Integration tests (hit real APIs)
# ──────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_hn_integration():
    """Algolia should return results for common queries."""
    result, error = await search_hn(query="python", limit=3)
    assert "pts" in result
    assert error is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_hn_empty_query_integration():
    """Top stories mode should return results."""
    result, error = await search_hn(query="", limit=3)
    assert "Found" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_url_integration():
    """Should read a known accessible URL."""
    result, error = await read_url("https://example.com")
    assert len(result) > 50
    assert error is None
