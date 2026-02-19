"""
Text-to-speech pipeline. Generates per-article MP3 files in parallel.
"""

import concurrent.futures as cf
import os
import threading
import time
from io import BytesIO
from pathlib import Path

from loguru import logger
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.config import settings
from app.models import (
    BriefingError,
    BriefingScript,
    ErrorSeverity,
    Job,
    JobPhase,
)

# ──────────────────────────────────────────────
# Sync OpenAI client (TTS runs in thread pool)
# ──────────────────────────────────────────────

_sync_client: OpenAI | None = None
_client_lock = threading.Lock()


def _get_sync_client() -> OpenAI:
    """Return a shared sync OpenAI client, creating it on first use. Thread-safe."""
    global _sync_client  # noqa: PLW0603
    if _sync_client is None:
        with _client_lock:
            if _sync_client is None:
                _sync_client = OpenAI(api_key=settings.openai_api_key)
    return _sync_client


# ──────────────────────────────────────────────
# Single-segment TTS
# ──────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(2),
    wait=wait_fixed(1),
    retry=retry_if_exception_type(Exception),
)
def tts_one_segment(text: str) -> bytes:
    """Generate MP3 audio for one text segment. Retries once on failure."""
    client = _get_sync_client()
    buffer = BytesIO()

    with client.audio.speech.with_streaming_response.create(
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        input=text,
        response_format="mp3",
        speed=settings.openai_tts_speed,
    ) as response:
        for chunk in response.iter_bytes():
            buffer.write(chunk)

    return buffer.getvalue()


# ──────────────────────────────────────────────
# File I/O
# ──────────────────────────────────────────────


def save_audio(job_id: str, index: int, audio_bytes: bytes) -> str:
    """Save MP3 bytes to disk. Returns filepath."""
    job_dir = Path(settings.audio_cache_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    filepath = str(job_dir / f"{index}.mp3")
    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    return filepath


# ──────────────────────────────────────────────
# Parallel TTS generation
# ──────────────────────────────────────────────


async def generate_all_audio(
    script: BriefingScript,
    job: Job,
) -> dict[int, str]:
    """
    Generate MP3 for each article in parallel.
    Returns {article_index: filepath}. Missing indices = failed articles.
    """
    job.progress.phase = JobPhase.TTS
    job.progress.message = "Generating audio..."

    results: dict[int, str] = {}
    errors: list[BriefingError] = []

    with cf.ThreadPoolExecutor(max_workers=settings.tts_max_workers) as executor:
        futures = {
            executor.submit(tts_one_segment, article.summary_text): i
            for i, article in enumerate(script.articles)
        }

        for future in cf.as_completed(futures):
            idx = futures[future]
            try:
                audio_bytes = future.result()
                filepath = save_audio(job.job_id, idx, audio_bytes)
                results[idx] = filepath
                logger.debug("[{}] TTS complete for article {}", job.job_id, idx)
            except Exception as e:
                logger.error("[{}] TTS failed for article {}: {}", job.job_id, idx, e)
                errors.append(
                    BriefingError(
                        code="tts_failed",
                        message=(
                            f"Audio generation failed for article {idx}: "
                            f"'{script.articles[idx].title[:50]}'"
                        ),
                        severity=ErrorSeverity.DEGRADED,
                        source="tts",
                        context={
                            "article_index": idx,
                            "article_title": script.articles[idx].title,
                            "exception": str(e),
                        },
                        recovered=True,
                        recovery_action="Article displayed without audio, transcript still available",
                    )
                )

    job.errors.extend(errors)

    # Check success rate
    total = len(script.articles)
    succeeded = len(results)

    if succeeded == 0:
        raise TTSCompleteFailureError(f"All {total} TTS calls failed")
    if succeeded / total < 0.5:
        raise TTSMajorityFailureError(f"Only {succeeded}/{total} articles generated audio")

    job.progress.message = f"Generated audio for {succeeded}/{total} articles"
    return results


# ──────────────────────────────────────────────
# Cleanup
# ──────────────────────────────────────────────


def cleanup_old_audio() -> None:
    """Delete audio files older than TTL. Called on startup and periodically."""
    cache_dir = Path(settings.audio_cache_dir)
    if not cache_dir.exists():
        return

    cutoff = time.time() - (settings.audio_cache_ttl_hours * 3600)
    cleaned = 0

    for job_dir in cache_dir.iterdir():
        if not job_dir.is_dir():
            continue
        files = list(job_dir.glob("*.mp3"))
        if files and all(os.path.getmtime(f) < cutoff for f in files):
            for f in files:
                f.unlink()
            try:
                job_dir.rmdir()
            except OSError:
                logger.warning(
                    "Could not remove directory {}, it may contain non-MP3 files", job_dir
                )
            cleaned += 1

    if cleaned:
        logger.info("Cleaned up {} old briefing directories", cleaned)


# ──────────────────────────────────────────────
# Custom Exceptions
# ──────────────────────────────────────────────


class TTSCompleteFailureError(Exception):
    pass


class TTSMajorityFailureError(Exception):
    pass
