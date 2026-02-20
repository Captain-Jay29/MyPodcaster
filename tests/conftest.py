"""Shared fixtures for unit tests."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def _reset_http_client():
    """Reset the shared httpx client between tests.

    Each async test may run in a different event loop, so a client created
    in a previous test becomes stale (its connection pool is tied to the
    old loop).  Clearing the module-level singleton forces _get_http_client
    to create a fresh client in the current loop.
    """
    yield
    import app.tools as tools_mod

    if tools_mod._http_client is not None:
        tools_mod._http_client = None


@pytest.fixture
def mock_openai():
    """Mock AsyncOpenAI client for unit tests. Returns a mock client instance."""
    mock_client = AsyncMock()
    with patch("app.agent.get_openai_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_httpx():
    """Mock httpx.AsyncClient for tool tests. Returns a mock client instance."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    with patch("app.tools._get_http_client", return_value=mock_client):
        yield mock_client
