"""
API route handlers. Thin layer — delegates to jobs.py.
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.jobs import create_job, get_job, process_briefing, summarize_errors
from app.models import (
    BriefingStatusResponse,
    CreateBriefingRequest,
    CreateBriefingResponse,
    JobStatus,
)

router = APIRouter(prefix="/api")


@router.post("/briefings", status_code=202, response_model=CreateBriefingResponse)
async def create_briefing(
    request: CreateBriefingRequest,
    background_tasks: BackgroundTasks,
):
    """Create a new briefing job. Returns immediately with job_id."""
    job = create_job(
        interests=request.interests,
        num_articles=request.num_articles,
    )

    background_tasks.add_task(process_briefing, job)

    return CreateBriefingResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
    )


@router.get("/briefings/{job_id}", response_model=BriefingStatusResponse)
async def get_briefing_status(job_id: str):
    """Poll for job status and progress."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Job {job_id} not found"}},
        )

    warnings = summarize_errors([e for e in job.errors if e.recovered])

    return BriefingStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        result=job.result,
        error=job.error,
        warnings=warnings,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/briefings/{job_id}/audio/{article_index}")
async def get_article_audio(job_id: str, article_index: int):
    """Stream a single article's MP3 audio."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED or not job.result:
        raise HTTPException(status_code=400, detail="Briefing not ready")

    filepath = job.result.audio_files.get(article_index)
    if not filepath or not Path(filepath).exists():
        raise HTTPException(status_code=404, detail="Audio not available for this article")

    return FileResponse(
        filepath,
        media_type="audio/mpeg",
        filename=f"briefing-{job_id}-{article_index}.mp3",
    )
