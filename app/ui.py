"""
Gradio Blocks UI. Calls internal Python functions directly (same process).
"""

import asyncio
import contextlib
import os

import gradio as gr

from app.jobs import create_job, process_briefing
from app.models import JobStatus

MAX_ARTICLES = 15  # matches BriefingScript max_length

CUSTOM_CSS = """
.article-row {
    border-bottom: 1px solid var(--border-color-primary);
    padding: 12px 0 !important;
    gap: 16px !important;
    align-items: center !important;
}
.article-row:last-child {
    border-bottom: none;
}
"""

HEAD_HTML = """
<script src="https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.min.js"></script>
<script>
function _wsInitPlayer(el) {
    if (el.getAttribute('data-ws-ready')) return;
    el.setAttribute('data-ws-ready', '1');
    var url = el.getAttribute('data-audio-url');
    var waveDiv = el.querySelector('.ws-waveform');
    var btn = el.querySelector('.ws-play');
    var timeEl = el.querySelector('.ws-time');
    var ws = WaveSurfer.create({
        container: waveDiv,
        height: 32,
        waveColor: '#5a5a6e',
        progressColor: '#00b4ff',
        cursorColor: '#00b4ff',
        cursorWidth: 1,
        url: url
    });
    function fmt(s) {
        var m = Math.floor(s / 60);
        var sec = Math.floor(s % 60);
        return m + ':' + (sec < 10 ? '0' : '') + sec;
    }
    ws.on('ready', function() { timeEl.textContent = '0:00 / ' + fmt(ws.getDuration()); });
    ws.on('audioprocess', function() { timeEl.textContent = fmt(ws.getCurrentTime()) + ' / ' + fmt(ws.getDuration()); });
    ws.on('seeking', function() { timeEl.textContent = fmt(ws.getCurrentTime()) + ' / ' + fmt(ws.getDuration()); });
    ws.on('play', function() { btn.textContent = '⏸'; });
    ws.on('pause', function() { btn.textContent = '▶'; });
    ws.on('finish', function() { btn.textContent = '▶'; });
    btn.addEventListener('click', function() { ws.playPause(); });
    var speedBtn = el.querySelector('.ws-speed');
    var speeds = [1, 1.5, 2];
    var speedIdx = 0;
    speedBtn.addEventListener('click', function() {
        speedIdx = (speedIdx + 1) % speeds.length;
        ws.setPlaybackRate(speeds[speedIdx]);
        speedBtn.textContent = speeds[speedIdx] + 'x';
    });
}
function _wsScanAll() {
    if (typeof WaveSurfer === 'undefined') { setTimeout(_wsScanAll, 100); return; }
    document.querySelectorAll('.ws-player:not([data-ws-ready])').forEach(_wsInitPlayer);
}
new MutationObserver(function() { _wsScanAll(); }).observe(document.body, {childList: true, subtree: true});
_wsScanAll();
</script>
"""


def wavesurfer_html(audio_path: str) -> str:
    """Return HTML for a minimalist WaveSurfer.js player."""
    return f"""
<div class="ws-player" data-audio-url="/gradio_api/file={audio_path}" style="width:100%;">
  <div class="ws-waveform" style="width:100%; height:32px;"></div>
  <div style="display:flex; align-items:center; gap:8px; margin-top:4px;">
    <button class="ws-play"
            style="background:none; border:none; cursor:pointer; color:#00b4ff; font-size:18px; padding:0; line-height:1;"
            aria-label="Play/Pause">▶</button>
    <span class="ws-time" style="font-size:11px; color:#00b4ff; font-family:monospace; flex:1;">
      0:00 / 0:00
    </span>
    <button class="ws-speed"
            style="background:none; border:1px solid #00b4ff; border-radius:4px; cursor:pointer; color:#00b4ff; font-size:10px; padding:1px 5px; font-family:monospace; line-height:1.4;"
            aria-label="Playback speed">1x</button>
  </div>
</div>
"""


def _hidden_outputs():
    """Return all article card outputs in hidden state."""
    rows = tuple(gr.Row(visible=False) for _ in range(MAX_ARTICLES))
    markdowns = tuple(gr.Markdown("") for _ in range(MAX_ARTICLES))
    audios = tuple(gr.HTML("", visible=False) for _ in range(MAX_ARTICLES))
    return rows, markdowns, audios


async def generate_briefing_handler(interests: str):
    """
    Gradio handler. Creates a job, processes it, yields progress updates.
    Yields: (status_markdown, *row_updates, *markdown_updates, *audio_updates)
    """
    job = create_job(interests=interests.strip(), num_articles=10)

    # Start background processing
    task = asyncio.create_task(process_briefing(job))

    # Hidden cards during progress
    hidden_rows, hidden_markdowns, hidden_audios = _hidden_outputs()

    # Poll and yield progress
    while job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        await asyncio.sleep(1.5)
        yield (
            f"**{job.progress.phase.value.upper()}** | {job.progress.message}",
            *hidden_rows,
            *hidden_markdowns,
            *hidden_audios,
        )

    # Wait for task to fully complete
    with contextlib.suppress(Exception):
        await task

    if job.status == JobStatus.FAILED:
        error_msg = job.error.message if job.error else "Unknown error"
        yield (f"**FAILED** | {error_msg}", *hidden_rows, *hidden_markdowns, *hidden_audios)
        return

    if not job.result:
        yield (
            "**FAILED** | No result produced",
            *hidden_rows,
            *hidden_markdowns,
            *hidden_audios,
        )
        return

    # Build per-article card outputs
    row_updates = []
    markdown_updates = []
    audio_updates = []

    for i, article in enumerate(job.result.articles):
        audio_path = job.result.audio_files.get(i)
        hn_url = f"https://news.ycombinator.com/item?id={article.hn_id}"

        row_updates.append(gr.Row(visible=True))
        markdown_updates.append(
            gr.Markdown(
                f"**{i + 1}. [{article.title}]({article.url})** "
                f"({article.points} pts, {article.num_comments} comments) "
                f"| [HN]({hn_url})\n\n"
                f"> {article.summary_text}"
            )
        )

        if audio_path:
            real_path = os.path.realpath(audio_path)
            audio_updates.append(gr.HTML(value=wavesurfer_html(real_path), visible=True))
        else:
            audio_updates.append(gr.HTML("", visible=False))

    # Hide remaining unused slots
    for _ in range(MAX_ARTICLES - len(job.result.articles)):
        row_updates.append(gr.Row(visible=False))
        markdown_updates.append(gr.Markdown(""))
        audio_updates.append(gr.HTML("", visible=False))

    succeeded = sum(1 for f in job.result.audio_files.values() if f)
    total = len(job.result.articles)
    status_msg = f"**DONE** | {succeeded}/{total} articles with audio"
    if job.errors:
        status_msg += f" | {len(job.errors)} warnings"

    yield (status_msg, *row_updates, *markdown_updates, *audio_updates)


def build_ui() -> gr.Blocks:
    """Build and return the Gradio Blocks UI."""
    with gr.Blocks(
        title="Audio Briefing Engine",
    ) as demo:
        gr.Markdown(
            "# Audio Briefing Engine\n"
            "Generate ~30-second audio summaries of top Hacker News articles.\n"
            "Enter topics you're interested in, or leave blank for today's top stories."
        )

        with gr.Row():
            interests_input = gr.Textbox(
                label="Interests (optional)",
                placeholder="e.g. AI, Rust, startup funding, climate tech",
                lines=1,
                scale=3,
            )
            generate_btn = gr.Button("Generate Briefing", variant="primary", scale=1)

        status_output = gr.Markdown("Ready. Click 'Generate Briefing' to start.")

        # Article cards — one row per possible article, hidden until populated
        article_rows = []
        article_markdowns = []
        article_audios = []

        for _i in range(MAX_ARTICLES):
            with gr.Row(visible=False, elem_classes=["article-row"]) as row:
                with gr.Column(scale=3):
                    md = gr.Markdown("")
                with gr.Column(scale=1, min_width=220):
                    audio = gr.HTML(
                        value="",
                        visible=False,
                    )
            article_rows.append(row)
            article_markdowns.append(md)
            article_audios.append(audio)

        generate_btn.click(
            fn=generate_briefing_handler,
            inputs=[interests_input],
            outputs=[
                status_output,
                *article_rows,
                *article_markdowns,
                *article_audios,
            ],
        )

    return demo  # type: ignore[no-any-return]
