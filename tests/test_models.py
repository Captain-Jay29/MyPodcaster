"""Unit tests for Pydantic models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import (
    ArticleSummary,
    BriefingError,
    BriefingScript,
    CreateBriefingRequest,
    ErrorSeverity,
    Job,
    JobPhase,
    JobProgress,
    JobStatus,
)

# ── ErrorSeverity ──


def test_error_severity_ordering():
    """ErrorSeverity values should be orderable for worst-case selection."""
    severities = list(ErrorSeverity)
    assert severities == [
        ErrorSeverity.RECOVERABLE,
        ErrorSeverity.DEGRADED,
        ErrorSeverity.FATAL,
    ]


# ── BriefingError ──


def test_briefing_error_defaults():
    """BriefingError should have sensible defaults."""
    err = BriefingError(
        code="test",
        message="something failed",
        severity=ErrorSeverity.RECOVERABLE,
        source="test_source",
    )
    assert err.context == {}
    assert err.recovered is False
    assert err.recovery_action == ""
    assert err.timestamp.tzinfo is not None  # timezone-aware


def test_briefing_error_timestamp_is_utc():
    """Timestamp should be timezone-aware UTC."""
    err = BriefingError(
        code="test",
        message="test",
        severity=ErrorSeverity.FATAL,
        source="test",
    )
    before = datetime.now(UTC)
    assert err.timestamp <= before


# ── ArticleSummary ──


def test_article_summary_audio_url_defaults_none():
    """audio_url should default to None before TTS."""
    article = ArticleSummary(
        title="Test",
        url="https://example.com",
        hn_id="123",
        points=100,
        summary_text="A test summary.",
    )
    assert article.audio_url is None
    assert article.num_comments == 0


# ── BriefingScript ──


def test_briefing_script_min_articles():
    """BriefingScript requires at least 1 article."""
    with pytest.raises(ValidationError):
        BriefingScript(articles=[])


def test_briefing_script_max_articles():
    """BriefingScript allows at most 15 articles."""
    articles = [
        ArticleSummary(
            title=f"Article {i}",
            url=f"https://example.com/{i}",
            hn_id=str(i),
            points=100,
            summary_text="Summary.",
        )
        for i in range(16)
    ]
    with pytest.raises(ValidationError):
        BriefingScript(articles=articles)


def test_briefing_script_valid():
    """BriefingScript with valid articles should parse."""
    script = BriefingScript(
        articles=[
            ArticleSummary(
                title="Test",
                url="https://example.com",
                hn_id="1",
                points=50,
                summary_text="A summary.",
            )
        ]
    )
    assert len(script.articles) == 1


# ── Job ──


def test_job_defaults():
    """Job should have correct defaults."""
    job = Job(job_id="abc123")
    assert job.status == JobStatus.PENDING
    assert job.progress.phase == JobPhase.PENDING
    assert job.result is None
    assert job.error is None
    assert job.errors == []
    assert job.interests == ""
    assert job.num_articles == 10
    assert job.completed_at is None
    assert job.created_at.tzinfo is not None  # timezone-aware


def test_job_created_at_is_utc():
    """Job.created_at should be timezone-aware UTC."""
    job = Job(job_id="test")
    before = datetime.now(UTC)
    assert job.created_at <= before


# ── JobProgress ──


def test_job_progress_defaults():
    """JobProgress defaults should be sensible."""
    progress = JobProgress()
    assert progress.phase == JobPhase.PENDING
    assert progress.articles_found == 0
    assert progress.articles_read == 0
    assert progress.message == "Waiting to start..."


# ── CreateBriefingRequest ──


def test_create_briefing_request_defaults():
    """Request defaults should be valid."""
    req = CreateBriefingRequest()
    assert req.interests == ""
    assert req.num_articles == 10


def test_create_briefing_request_validation():
    """num_articles should be bounded."""
    with pytest.raises(ValidationError):
        CreateBriefingRequest(num_articles=2)  # below min 3

    with pytest.raises(ValidationError):
        CreateBriefingRequest(num_articles=16)  # above max 15


def test_create_briefing_request_interests_max_length():
    """Interests field should enforce max length."""
    with pytest.raises(ValidationError):
        CreateBriefingRequest(interests="x" * 501)
