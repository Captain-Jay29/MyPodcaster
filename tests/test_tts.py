"""Unit tests for TTS pipeline."""

import tempfile
from pathlib import Path

from app.tts import save_audio

# ── save_audio ──


def test_save_audio_creates_file():
    """save_audio should write MP3 bytes to the correct path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from unittest.mock import patch

        with patch("app.tts.settings") as mock_settings:
            mock_settings.audio_cache_dir = tmpdir

            filepath = save_audio("testjob", 0, b"fake-mp3-data")

            assert Path(filepath).exists()
            assert Path(filepath).read_bytes() == b"fake-mp3-data"
            assert "testjob" in filepath
            assert "0.mp3" in filepath


def test_save_audio_creates_subdirectory():
    """save_audio should create the job subdirectory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from unittest.mock import patch

        with patch("app.tts.settings") as mock_settings:
            mock_settings.audio_cache_dir = tmpdir

            save_audio("newjob", 3, b"data")

            job_dir = Path(tmpdir) / "newjob"
            assert job_dir.is_dir()
            assert (job_dir / "3.mp3").exists()
