"""Shared fixtures for unit tests."""

from unittest.mock import patch

import pytest


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for unit tests."""
    with patch("app.agent.get_openai_client") as mock:
        yield mock


@pytest.fixture
def mock_httpx():
    """Mock httpx for tool tests."""
    with patch("app.tools._get_http_client") as mock:
        yield mock
