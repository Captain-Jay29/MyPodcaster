"""
Gradio Blocks UI. Calls internal Python functions directly (same process).
"""

import asyncio
import contextlib

import gradio as gr

from app.jobs import create_job, process_briefing
from app.models import JobStatus

MAX_ARTICLES = 15  # matches BriefingScript max_length


async def generate_briefing_handler(interests: str):
    """
    Gradio handler. Creates a job, processes it, yields progress updates.
    Yields: (articles_markdown, status_markdown, *audio_updates)
    """
    job = create_job(interests=interests.strip(), num_articles=10)

    # Start background processing
    task = asyncio.create_task(process_briefing(job))

    # Hidden audio players during progress
    hidden_audios = tuple(gr.Audio(visible=False) for _ in range(MAX_ARTICLES))

    # Poll and yield progress
    while job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        await asyncio.sleep(1.5)
        yield (
            "",
            f"**{job.progress.phase.value.upper()}** | {job.progress.message}",
            *hidden_audios,
        )

    # Wait for task to fully complete
    with contextlib.suppress(Exception):
        await task

    if job.status == JobStatus.FAILED:
        error_msg = job.error.message if job.error else "Unknown error"
        yield ("", f"**FAILED** | {error_msg}", *hidden_audios)
        return

    if not job.result:
        yield ("", "**FAILED** | No result produced", *hidden_audios)
        return

    # Build article markdown
    articles_md_lines = []
    audio_updates = []

    for i, article in enumerate(job.result.articles):
        audio_path = job.result.audio_files.get(i)

        hn_url = f"https://news.ycombinator.com/item?id={article.hn_id}"
        articles_md_lines.append(
            f"**{i + 1}. [{article.title}]({article.url})** "
            f"({article.points} pts, {article.num_comments} comments) "
            f"| [HN Discussion]({hn_url})\n\n"
            f"> {article.summary_text}\n"
        )

        if audio_path:
            audio_updates.append(
                gr.Audio(value=audio_path, visible=True, label=f"{i + 1}. {article.title}")
            )
        else:
            audio_updates.append(
                gr.Audio(visible=True, label=f"{i + 1}. {article.title} (no audio)")
            )

    # Hide remaining unused audio slots
    for _ in range(MAX_ARTICLES - len(job.result.articles)):
        audio_updates.append(gr.Audio(visible=False))

    articles_md = "\n---\n\n".join(articles_md_lines)

    succeeded = sum(1 for f in job.result.audio_files.values() if f)
    total = len(job.result.articles)
    status_msg = f"**DONE** | {succeeded}/{total} articles with audio"
    if job.errors:
        status_msg += f" | {len(job.errors)} warnings"

    yield (articles_md, status_msg, *audio_updates)


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
        articles_output = gr.Markdown(label="Articles")

        # Audio players — one per possible article, hidden until populated
        audio_outputs = []
        for i in range(MAX_ARTICLES):
            audio = gr.Audio(label=f"Article {i + 1}", visible=False)
            audio_outputs.append(audio)

        generate_btn.click(
            fn=generate_briefing_handler,
            inputs=[interests_input],
            outputs=[articles_output, status_output, *audio_outputs],
        )

    return demo  # type: ignore[no-any-return]
