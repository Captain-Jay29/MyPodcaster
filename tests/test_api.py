"""Unit tests for API endpoints."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models import (
    ArticleSummary,
    JobResult,
    JobStatus,
)


@pytest.fixture
def client():
    """Create a test client that doesn't run background tasks."""
    # Import here to avoid config validation at collection time
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_job_store():
    """Clear job store between tests."""
    from app.jobs import _jobs

    _jobs.clear()
    yield
    _jobs.clear()


# ── POST /api/briefings ──


def test_create_briefing(client):
    resp = client.post(
        "/api/briefings",
        json={"interests": "AI", "num_articles": 5},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert "created_at" in data


def test_create_briefing_defaults(client):
    resp = client.post("/api/briefings", json={})
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"


def test_create_briefing_validation_error(client):
    resp = client.post(
        "/api/briefings",
        json={"num_articles": 100},  # exceeds max 15
    )
    assert resp.status_code == 422


# ── GET /api/briefings/{job_id} ──


def test_get_briefing_status_found(client):
    from app.jobs import create_job

    # Create job directly to avoid triggering background task
    job = create_job(interests="Rust")

    resp = client.get(f"/api/briefings/{job.job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == job.job_id
    assert data["status"] == "pending"
    assert "progress" in data


def test_get_briefing_status_not_found(client):
    resp = client.get("/api/briefings/nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"]["error"]["code"] == "not_found"


# ── GET /api/briefings/{job_id}/audio/{article_index} ──


def test_get_audio_not_found_job(client):
    resp = client.get("/api/briefings/nonexistent/audio/0")
    assert resp.status_code == 404


def test_get_audio_not_ready(client):
    from app.jobs import create_job

    job = create_job()
    # Job is still pending, not completed

    resp = client.get(f"/api/briefings/{job.job_id}/audio/0")
    assert resp.status_code == 400
    data = resp.json()
    assert data["detail"]["error"]["code"] == "not_ready"


def test_get_audio_success(client):
    from app.jobs import create_job

    job = create_job()
    job.status = JobStatus.COMPLETED

    # Create a temporary MP3 file
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"\xff\xfb\x90\x00" * 100)  # fake MP3 data
        tmp_path = f.name

    try:
        job.result = JobResult(
            articles=[
                ArticleSummary(
                    title="Test",
                    url="https://example.com",
                    hn_id="1",
                    points=100,
                    summary_text="Summary.",
                    audio_url=f"/api/briefings/{job.job_id}/audio/0",
                )
            ],
            audio_files={0: tmp_path},
        )

        resp = client.get(f"/api/briefings/{job.job_id}/audio/0")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_get_audio_missing_index(client):
    from app.jobs import create_job

    job = create_job()
    job.status = JobStatus.COMPLETED
    job.result = JobResult(
        articles=[
            ArticleSummary(
                title="Test",
                url="https://example.com",
                hn_id="1",
                points=100,
                summary_text="Summary.",
            )
        ],
        audio_files={},  # no audio generated
    )

    resp = client.get(f"/api/briefings/{job.job_id}/audio/0")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"]["error"]["code"] == "audio_not_found"
