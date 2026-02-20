"""Tests for app/ui.py — WaveSurfer.js audio player and Gradio UI."""

import gradio as gr

from app.ui import (
    CUSTOM_CSS,
    HEAD_HTML,
    MAX_ARTICLES,
    _hidden_outputs,
    build_ui,
    wavesurfer_html,
)

# ──────────────────────────────────────────────
# wavesurfer_html
# ──────────────────────────────────────────────


class TestWavesurferHtml:
    def test_contains_audio_url(self):
        html = wavesurfer_html("/tmp/test.mp3")
        assert 'data-audio-url="/gradio_api/file=/tmp/test.mp3"' in html

    def test_contains_waveform_div(self):
        html = wavesurfer_html("/tmp/test.mp3")
        assert 'class="ws-waveform"' in html

    def test_contains_play_button(self):
        html = wavesurfer_html("/tmp/test.mp3")
        assert 'class="ws-play"' in html

    def test_contains_time_display(self):
        html = wavesurfer_html("/tmp/test.mp3")
        assert 'class="ws-time"' in html
        assert "0:00 / 0:00" in html

    def test_contains_speed_button(self):
        html = wavesurfer_html("/tmp/test.mp3")
        assert 'class="ws-speed"' in html
        assert "1x" in html

    def test_wraps_in_ws_player_div(self):
        html = wavesurfer_html("/tmp/test.mp3")
        assert 'class="ws-player"' in html

    def test_different_paths_produce_different_urls(self):
        html_a = wavesurfer_html("/tmp/a.mp3")
        html_b = wavesurfer_html("/tmp/b.mp3")
        assert "/tmp/a.mp3" in html_a
        assert "/tmp/b.mp3" in html_b
        assert "/tmp/b.mp3" not in html_a


# ──────────────────────────────────────────────
# HEAD_HTML — WaveSurfer CDN + MutationObserver
# ──────────────────────────────────────────────


class TestHeadHtml:
    def test_loads_wavesurfer_cdn(self):
        assert "wavesurfer.js@7" in HEAD_HTML
        assert "<script" in HEAD_HTML

    def test_contains_mutation_observer(self):
        assert "MutationObserver" in HEAD_HTML

    def test_contains_init_function(self):
        assert "_wsInitPlayer" in HEAD_HTML
        assert "_wsScanAll" in HEAD_HTML

    def test_contains_speed_control_logic(self):
        assert "setPlaybackRate" in HEAD_HTML
        assert "speeds" in HEAD_HTML

    def test_marks_initialized_players(self):
        assert "data-ws-ready" in HEAD_HTML


# ──────────────────────────────────────────────
# _hidden_outputs
# ──────────────────────────────────────────────


class TestHiddenOutputs:
    def test_returns_three_tuples(self):
        rows, markdowns, audios = _hidden_outputs()
        assert len(rows) == MAX_ARTICLES
        assert len(markdowns) == MAX_ARTICLES
        assert len(audios) == MAX_ARTICLES

    def test_rows_are_invisible(self):
        rows, _, _ = _hidden_outputs()
        for row in rows:
            assert isinstance(row, gr.Row)

    def test_audios_are_gr_html(self):
        """Audio slots should be gr.HTML, not gr.Audio."""
        _, _, audios = _hidden_outputs()
        for audio in audios:
            assert isinstance(audio, gr.HTML)


# ──────────────────────────────────────────────
# build_ui
# ──────────────────────────────────────────────


class TestBuildUi:
    def test_returns_gradio_blocks(self):
        demo = build_ui()
        assert isinstance(demo, gr.Blocks)

    def test_has_correct_title(self):
        demo = build_ui()
        assert demo.title == "Audio Briefing Engine"


# ──────────────────────────────────────────────
# CUSTOM_CSS
# ──────────────────────────────────────────────


class TestCustomCss:
    def test_contains_article_row_styles(self):
        assert ".article-row" in CUSTOM_CSS

    def test_no_old_audio_player_styles(self):
        """Old gr.Audio CSS classes should not be present."""
        assert ".audio-player" not in CUSTOM_CSS
        assert "#e8f0fe" not in CUSTOM_CSS
