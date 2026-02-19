"""Shared fixtures for unit tests."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest


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
