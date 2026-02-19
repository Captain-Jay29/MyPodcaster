"""
In-memory job store. Manages lifecycle of briefing generation jobs.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from loguru import logger

from app.agent import AgentTimeoutError, run_agent
from app.models import (
    BriefingError,
    ErrorDetail,
    ErrorSeverity,
    Job,
    JobError,
    JobPhase,
    JobResult,
    JobStatus,
)
from app.tts import (
    TTSCompleteFailureError,
    TTSMajorityFailureError,
    generate_all_audio,
)

# ──────────────────────────────────────────────
# Job Store (in-memory)
# ──────────────────────────────────────────────

_jobs: dict[str, Job] = {}


def create_job(interests: str = "", num_articles: int = 10) -> Job:
    """Create a new job and store it. Returns the job."""
    job_id = uuid.uuid4().hex[:12]
    job = Job(
        job_id=job_id,
        interests=interests,
        num_articles=num_articles,
    )
    _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Job | None:
    """Look up a job by ID."""
    return _jobs.get(job_id)


def cleanup_old_jobs() -> None:
    """Remove jobs older than the audio cache TTL. Called alongside cleanup_old_audio."""
    from app.config import settings

    cutoff = datetime.now(UTC) - timedelta(hours=settings.audio_cache_ttl_hours)
    expired = [jid for jid, j in _jobs.items() if j.created_at < cutoff]
    for jid in expired:
        del _jobs[jid]

    if expired:
        logger.info("Cleaned up {} expired jobs", len(expired))


# ──────────────────────────────────────────────
# Error Summarization
# ──────────────────────────────────────────────


def summarize_errors(errors: list[BriefingError]) -> list[ErrorDetail]:
    """Group errors by source component for the API response."""
    by_source: dict[str, list[BriefingError]] = defaultdict(list)
    for e in errors:
        by_source[e.source].append(e)

    details = []
    for source, errs in by_source.items():
        worst = max(errs, key=lambda e: list(ErrorSeverity).index(e.severity))
        details.append(
            ErrorDetail(
                component=source,
                count=len(errs),
                sample=worst.message,
                severity=worst.severity.value,
            )
        )

    return details


# ──────────────────────────────────────────────
# Job Processing (background task)
# ──────────────────────────────────────────────


async def process_briefing(job: Job) -> None:
    """
    Top-level orchestrator. Catches everything, never crashes.
    Updates job status/progress throughout.
    """
    try:
        job.status = JobStatus.PROCESSING

        # ── Agent phase ──
        job.progress.phase = JobPhase.AGENT
        job.progress.message = "Starting agent..."
        script = await run_agent(job.interests, job.num_articles, job)

        # ── TTS phase ──
        audio_files = await generate_all_audio(script, job)

        # ── Build result ──
        for i, article in enumerate(script.articles):
            if i in audio_files:
                article.audio_url = f"/api/briefings/{job.job_id}/audio/{i}"

        job.status = JobStatus.COMPLETED
        job.progress.phase = JobPhase.DONE
        job.progress.message = "Done!"
        job.result = JobResult(
            articles=script.articles,
            audio_files=audio_files,
        )
        job.completed_at = datetime.now(UTC)

        if job.errors:
            logger.warning("Job {} completed with {} errors", job.job_id, len(job.errors))
        else:
            logger.info("Job {} completed successfully", job.job_id)

    except (AgentTimeoutError, TimeoutError) as e:
        job.status = JobStatus.FAILED
        job.error = JobError(
            code=job.errors[-1].code if job.errors else "agent_error",
            message=str(e),
            details=summarize_errors(job.errors),
        )
        logger.error("Job {} failed (agent): {}", job.job_id, e)

    except (TTSCompleteFailureError, TTSMajorityFailureError) as e:
        job.status = JobStatus.FAILED
        job.error = JobError(
            code="tts_failure",
            message=str(e),
            details=summarize_errors(job.errors),
        )
        logger.error("Job {} failed (TTS): {}", job.job_id, e)

    except Exception as e:
        logger.exception("Unexpected error in job {}", job.job_id)
        job.status = JobStatus.FAILED
        job.error = JobError(
            code="internal_error",
            message=f"Unexpected error: {type(e).__name__}: {e!s}",
            details=summarize_errors(job.errors),
        )
