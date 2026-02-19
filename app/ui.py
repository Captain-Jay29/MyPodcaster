"""
Gradio Blocks UI. Calls internal Python functions directly (same process).
"""

import asyncio

import gradio as gr

from app.jobs import create_job, process_briefing
from app.models import JobStatus


async def generate_briefing_handler(interests: str):
    """
    Gradio handler. Creates a job, processes it, yields progress updates.
    Yields: (audio_list, articles_markdown, status_markdown)
    """
    job = create_job(interests=interests.strip(), num_articles=10)

    # Start background processing
    task = asyncio.create_task(process_briefing(job))

    # Poll and yield progress
    while job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        await asyncio.sleep(1.5)
        yield (
            [],
            "",
            f"**{job.progress.phase.value.upper()}** | {job.progress.message}",
        )

    # Wait for task to fully complete
    await task

    if job.status == JobStatus.FAILED:
        error_msg = job.error.message if job.error else "Unknown error"
        yield ([], "", f"**FAILED** | {error_msg}")
        return

    if not job.result:
        yield ([], "", "**FAILED** | No result produced")
        return

    # Build outputs
    audio_list = []
    articles_md_lines = []

    for i, article in enumerate(job.result.articles):
        audio_path = job.result.audio_files.get(i)
        audio_list.append(audio_path)

        hn_url = f"https://news.ycombinator.com/item?id={article.hn_id}"
        status = "Audio available" if audio_path else "Transcript only"
        articles_md_lines.append(
            f"**{i + 1}. [{article.title}]({article.url})** "
            f"({article.points} pts, {article.num_comments} comments) "
            f"| [HN Discussion]({hn_url}) | _{status}_\n\n"
            f"> {article.summary_text}\n"
        )

    articles_md = "\n---\n\n".join(articles_md_lines)

    succeeded = sum(1 for a in audio_list if a is not None)
    total = len(audio_list)
    status_msg = f"**DONE** | {succeeded}/{total} articles with audio"
    if job.errors:
        status_msg += f" | {len(job.errors)} warnings"

    yield (audio_list, articles_md, status_msg)


def build_ui() -> gr.Blocks:
    """Build and return the Gradio Blocks UI."""
    with gr.Blocks(
        title="Audio Briefing Engine",
        theme=gr.themes.Soft(),
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

        generate_btn.click(
            fn=generate_briefing_handler,
            inputs=[interests_input],
            outputs=[
                gr.JSON(visible=False),  # audio list placeholder
                articles_output,
                status_output,
            ],
        )

    return demo  # type: ignore[no-any-return]
