"""Unit tests for job store and orchestrator."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models import (
    ArticleSummary,
    BriefingError,
    BriefingScript,
    ErrorSeverity,
    Job,
    JobStatus,
)

# Use deferred imports to avoid circular import issues at collection time
# app.jobs imports app.agent and app.tts at module level


@pytest.fixture(autouse=True)
def _clear_job_store():
    """Clear the in-memory job store between tests."""
    from app.jobs import _jobs

    _jobs.clear()
    yield
    _jobs.clear()


# ── create_job / get_job ──


def test_create_job_returns_job():
    from app.jobs import create_job

    job = create_job(interests="AI", num_articles=5)
    assert isinstance(job, Job)
    assert job.interests == "AI"
    assert job.num_articles == 5
    assert job.status == JobStatus.PENDING
    assert len(job.job_id) == 12


def test_create_job_unique_ids():
    from app.jobs import create_job

    job1 = create_job()
    job2 = create_job()
    assert job1.job_id != job2.job_id


def test_get_job_found():
    from app.jobs import create_job, get_job

    job = create_job()
    found = get_job(job.job_id)
    assert found is not None
    assert found.job_id == job.job_id


def test_get_job_not_found():
    from app.jobs import get_job

    assert get_job("nonexistent") is None


# ── cleanup_old_jobs ──


def test_cleanup_old_jobs_removes_expired():
    from app.jobs import _jobs, cleanup_old_jobs, create_job

    job = create_job()
    # Backdate the job to 25 hours ago
    job.created_at = datetime.now(UTC) - timedelta(hours=25)

    assert len(_jobs) == 1
    cleanup_old_jobs()
    assert len(_jobs) == 0


def test_cleanup_old_jobs_keeps_recent():
    from app.jobs import _jobs, cleanup_old_jobs, create_job

    create_job()  # created just now
    assert len(_jobs) == 1
    cleanup_old_jobs()
    assert len(_jobs) == 1


# ── summarize_errors ──


def test_summarize_errors_empty():
    from app.jobs import summarize_errors

    result = summarize_errors([])
    assert result == []


def test_summarize_errors_groups_by_source():
    from app.jobs import summarize_errors

    errors = [
        BriefingError(
            code="err1",
            message="first",
            severity=ErrorSeverity.RECOVERABLE,
            source="tools.search_hn",
        ),
        BriefingError(
            code="err2",
            message="second (worse)",
            severity=ErrorSeverity.DEGRADED,
            source="tools.search_hn",
        ),
        BriefingError(
            code="err3",
            message="tts fail",
            severity=ErrorSeverity.FATAL,
            source="tts",
        ),
    ]
    details = summarize_errors(errors)

    assert len(details) == 2  # two source groups

    hn_detail = next(d for d in details if d.component == "tools.search_hn")
    assert hn_detail.count == 2
    assert hn_detail.severity == "degraded"  # worst of the two
    assert hn_detail.sample == "second (worse)"

    tts_detail = next(d for d in details if d.component == "tts")
    assert tts_detail.count == 1
    assert tts_detail.severity == "fatal"


# ── process_briefing ──


def _make_script():
    """Helper to create a minimal BriefingScript."""
    return BriefingScript(
        articles=[
            ArticleSummary(
                title="Test Article",
                url="https://example.com",
                hn_id="123",
                points=100,
                summary_text="A test summary for audio generation.",
            )
        ]
    )


@pytest.mark.asyncio
async def test_process_briefing_success():
    from app.jobs import create_job, process_briefing

    job = create_job(interests="AI", num_articles=3)
    script = _make_script()

    with (
        patch("app.jobs.run_agent", new_callable=AsyncMock, return_value=script),
        patch(
            "app.jobs.generate_all_audio",
            new_callable=AsyncMock,
            return_value={0: "/tmp/test.mp3"},
        ),
    ):
        await process_briefing(job)

    assert job.status == JobStatus.COMPLETED
    assert job.result is not None
    assert len(job.result.articles) == 1
    assert job.result.articles[0].audio_url == f"/api/briefings/{job.job_id}/audio/0"
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_process_briefing_agent_timeout():
    from app.agent import AgentTimeoutError
    from app.jobs import create_job, process_briefing

    job = create_job()

    with patch(
        "app.jobs.run_agent",
        new_callable=AsyncMock,
        side_effect=AgentTimeoutError("timed out"),
    ):
        await process_briefing(job)

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert "timed out" in job.error.message


@pytest.mark.asyncio
async def test_process_briefing_tts_failure():
    from app.jobs import create_job, process_briefing
    from app.tts import TTSCompleteFailureError

    job = create_job()
    script = _make_script()

    with (
        patch("app.jobs.run_agent", new_callable=AsyncMock, return_value=script),
        patch(
            "app.jobs.generate_all_audio",
            new_callable=AsyncMock,
            side_effect=TTSCompleteFailureError("all failed"),
        ),
    ):
        await process_briefing(job)

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.code == "tts_failure"


@pytest.mark.asyncio
async def test_process_briefing_unexpected_error():
    from app.jobs import create_job, process_briefing

    job = create_job()

    with patch(
        "app.jobs.run_agent",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        await process_briefing(job)

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.code == "internal_error"
    assert "RuntimeError" in job.error.message
