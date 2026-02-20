"""
Entry point. Creates FastAPI app, mounts Gradio, sets up lifespan.
"""

import contextlib
import os
from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI
from loguru import logger

from app.api import router
from app.config import settings
from app.jobs import cleanup_old_jobs
from app.tools import close_http_client
from app.tts import cleanup_old_audio
from app.ui import CUSTOM_CSS, HEAD_HTML, build_ui

# ──────────────────────────────────────────────
# Sentry (optional)
# ──────────────────────────────────────────────

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(settings.sentry_dsn)


# ──────────────────────────────────────────────
# Lifespan (startup/shutdown)
# ──────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Audio Briefing Engine on port {}", settings.port)
    logger.info("Model: {}, TTS: {}", settings.openai_model, settings.openai_tts_model)
    with contextlib.suppress(Exception):
        cleanup_old_audio()
    cleanup_old_jobs()
    yield
    # Shutdown
    await close_http_client()
    logger.info("Shutting down...")


# ──────────────────────────────────────────────
# App Assembly
# ──────────────────────────────────────────────

app = FastAPI(
    title="Audio Briefing Engine",
    lifespan=lifespan,
)

# Mount API routes
app.include_router(router)

# Mount Gradio UI
demo = build_ui()
demo = demo.queue(max_size=20, default_concurrency_limit=5)
audio_dir = os.path.realpath(settings.audio_cache_dir)
gr.mount_gradio_app(
    app,
    demo,
    path="/",
    css=CUSTOM_CSS,
    head=HEAD_HTML,
    allowed_paths=[audio_dir],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
