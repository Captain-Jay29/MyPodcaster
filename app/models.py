"""
All data models in one place. No business logic except computed properties.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
# Error Models
# ──────────────────────────────────────────────


class ErrorSeverity(StrEnum):
    RECOVERABLE = "recoverable"
    DEGRADED = "degraded"
    FATAL = "fatal"


class BriefingError(BaseModel):
    code: str
    message: str
    severity: ErrorSeverity
    source: str
    context: dict = {}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    recovered: bool = False
    recovery_action: str = ""


class ErrorDetail(BaseModel):
    component: str
    count: int
    sample: str
    severity: str


class JobError(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


# ──────────────────────────────────────────────
# Agent Output Models
# ──────────────────────────────────────────────


class ArticleSummary(BaseModel):
    title: str = Field(description="Original article title from HN")
    url: str = Field(description="URL of the original article")
    hn_id: str = Field(description="Hacker News item ID")
    points: int = Field(description="HN points at time of fetch")
    num_comments: int = Field(default=0, description="HN comment count")
    summary_text: str = Field(
        description="60-80 word spoken summary. Self-contained, no markdown, "
        "no URLs. Written for audio: What happened, why it matters, what to watch."
    )
    audio_url: str | None = Field(
        default=None,
        description="Set after TTS: /api/briefings/{job_id}/audio/{index}",
    )


class BriefingScript(BaseModel):
    articles: list[ArticleSummary] = Field(
        min_length=1,
        max_length=15,
        description="Ordered list of article summaries, each independently playable",
    )


# ──────────────────────────────────────────────
# Job Models
# ──────────────────────────────────────────────


class JobPhase(StrEnum):
    PENDING = "pending"
    AGENT = "agent"
    TTS = "tts"
    DONE = "done"


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobProgress(BaseModel):
    phase: JobPhase = JobPhase.PENDING
    articles_found: int = 0
    articles_selected: int = 0
    articles_read: int = 0
    message: str = "Waiting to start..."


class JobResult(BaseModel):
    articles: list[ArticleSummary]
    audio_files: dict[int, str] = {}  # index -> filesystem path


class Job(BaseModel):
    job_id: str
    interests: str = ""
    num_articles: int = 10
    status: JobStatus = JobStatus.PENDING
    progress: JobProgress = Field(default_factory=JobProgress)
    result: JobResult | None = None
    error: JobError | None = None
    errors: list[BriefingError] = []  # all errors accumulated during processing
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


# ──────────────────────────────────────────────
# API Request/Response Models
# ──────────────────────────────────────────────


class CreateBriefingRequest(BaseModel):
    interests: str = Field(default="", max_length=500)
    num_articles: int = Field(default=10, ge=3, le=15)


class CreateBriefingResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime


class BriefingStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: JobProgress
    result: JobResult | None = None
    error: JobError | None = None
    warnings: list[ErrorDetail] = []
    created_at: datetime
    completed_at: datetime | None = None
