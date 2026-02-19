"""
Gradio Blocks UI. Calls internal Python functions directly (same process).
"""

import asyncio
import contextlib

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
.article-row .audio-player {
    min-width: 200px;
}

/* Compact audio player: fit waveform + duration without overlap */
.audio-player .minimal-audio-player {
    width: 100% !important;
    padding: var(--spacing-xs) var(--spacing-sm) !important;
    gap: var(--spacing-xs) !important;
    background: #e8f0fe !important;
    border-radius: var(--radius-md) !important;
}
.audio-player .waveform-wrapper {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    overflow: hidden !important;
}
.audio-player .timestamp {
    font-size: 11px !important;
    min-width: 32px !important;
}
/* Reduce waveform vertical height */
.audio-player .waveform-wrapper ::part(wrapper) {
    height: 24px !important;
    margin-bottom: 0 !important;
}
/* Light blue background for the full audio component area */
.audio-player .component-wrapper {
    padding: var(--spacing-xs) !important;
    background: #e8f0fe !important;
    border-radius: var(--radius-md) !important;
}
.audio-player .standard-player {
    padding: var(--spacing-xs) !important;
    background: #e8f0fe !important;
    border-radius: var(--radius-md) !important;
}
/* Reduce waveform height in standard player too */
.audio-player #waveform {
    height: 28px !important;
}
"""


def _hidden_outputs():
    """Return all article card outputs in hidden state."""
    rows = tuple(gr.Row(visible=False) for _ in range(MAX_ARTICLES))
    markdowns = tuple(gr.Markdown("") for _ in range(MAX_ARTICLES))
    audios = tuple(gr.Audio(visible=False) for _ in range(MAX_ARTICLES))
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
            audio_updates.append(gr.Audio(value=audio_path, visible=True))
        else:
            audio_updates.append(gr.Audio(visible=False))

    # Hide remaining unused slots
    for _ in range(MAX_ARTICLES - len(job.result.articles)):
        row_updates.append(gr.Row(visible=False))
        markdown_updates.append(gr.Markdown(""))
        audio_updates.append(gr.Audio(visible=False))

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
        css=CUSTOM_CSS,
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
                    audio = gr.Audio(
                        visible=False,
                        show_label=False,
                        elem_classes=["audio-player"],
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
