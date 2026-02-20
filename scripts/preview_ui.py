"""
Standalone UI preview — renders article cards with dummy audio.
Run: python scripts/preview_ui.py
No API keys or agent needed.
"""

import math
import os
import struct
import tempfile

import gradio as gr

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

# Load WaveSurfer.js globally via <head>
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

# Dummy articles
ARTICLES = [
    {
        "title": "OpenAI Releases GPT-5 with Native Tool Use",
        "url": "https://example.com/gpt5",
        "points": 842,
        "comments": 312,
        "hn_id": "39012345",
        "summary": (
            "OpenAI has released GPT-5 with native tool use built into the model. "
            "The new model can call APIs, run code, and browse the web without "
            "external scaffolding. Early benchmarks show a forty percent improvement "
            "on complex reasoning tasks. Developers can access it through the existing "
            "API with a new tools parameter."
        ),
    },
    {
        "title": "Rust 2.0 Announced at RustConf",
        "url": "https://example.com/rust2",
        "points": 567,
        "comments": 198,
        "hn_id": "39012346",
        "summary": (
            "The Rust team announced version two point zero at RustConf this week. "
            "Major changes include a simplified borrow checker, first-class async "
            "support, and a new edition system. Migration tooling handles most code "
            "automatically. The release is expected in Q3 this year."
        ),
    },
    {
        "title": "Show HN: I Built a Solar-Powered Home Server",
        "url": "https://example.com/solar-server",
        "points": 234,
        "comments": 87,
        "hn_id": "39012347",
        "summary": (
            "A developer built a fully solar-powered home server running on a "
            "Raspberry Pi five with a hundred watt solar panel. The system handles "
            "email, file storage, and a personal website. Total cost was under three "
            "hundred dollars. It has been running for six months with zero downtime."
        ),
    },
]


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


def generate_wav(duration_s: float = 5.0) -> str:
    """Generate a speech-like WAV with varying tones and pauses."""
    sample_rate = 22050
    n_samples = int(sample_rate * duration_s)
    samples = []

    import random
    random.seed(42)
    t = 0
    while t < n_samples:
        phrase_len = int(sample_rate * random.uniform(0.3, 0.8))
        base_freq = random.uniform(120, 220)
        for i in range(min(phrase_len, n_samples - t)):
            freq_wobble = base_freq * (1 + 0.02 * math.sin(2 * math.pi * 5 * i / sample_rate))
            val = (
                0.5 * math.sin(2 * math.pi * freq_wobble * i / sample_rate)
                + 0.25 * math.sin(2 * math.pi * freq_wobble * 2 * i / sample_rate)
                + 0.12 * math.sin(2 * math.pi * freq_wobble * 3 * i / sample_rate)
            )
            env = 1.0
            fade = int(sample_rate * 0.03)
            if i < fade:
                env = i / fade
            elif i > phrase_len - fade:
                env = (phrase_len - i) / fade
            samples.append(int(12000 * val * env))
        t += phrase_len

        pause_len = int(sample_rate * random.uniform(0.1, 0.4))
        for _ in range(min(pause_len, n_samples - t)):
            samples.append(0)
        t += pause_len

    samples = samples[:n_samples]

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)  # noqa: SIM115
    data_size = len(samples) * 2
    tmp.write(b"RIFF")
    tmp.write(struct.pack("<I", 36 + data_size))
    tmp.write(b"WAVE")
    tmp.write(b"fmt ")
    tmp.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
    tmp.write(b"data")
    tmp.write(struct.pack("<I", data_size))
    for s in samples:
        tmp.write(struct.pack("<h", max(-32768, min(32767, s))))
    tmp.close()
    return os.path.realpath(tmp.name)


def build_preview() -> gr.Blocks:
    sample = os.path.join(os.path.dirname(__file__), "harvard.wav")
    audio_files = [sample, sample, sample]

    with gr.Blocks(title="UI Preview") as demo:
        gr.Markdown(
            "# Audio Briefing Engine — UI Preview\n"
            "This is a standalone preview with dummy data. Edit "
            "`scripts/preview_ui.py` and refresh to iterate."
        )

        gr.Markdown("**DONE** | 3/3 articles with audio")

        for i, article in enumerate(ARTICLES):
            hn_url = f"https://news.ycombinator.com/item?id={article['hn_id']}"
            with gr.Row(elem_classes=["article-row"]):
                with gr.Column(scale=3):
                    gr.Markdown(
                        f"**{i + 1}. [{article['title']}]({article['url']})** "
                        f"({article['points']} pts, {article['comments']} comments) "
                        f"| [HN]({hn_url})\n\n"
                        f"> {article['summary']}"
                    )
                with gr.Column(scale=1, min_width=220):
                    gr.HTML(
                        value=wavesurfer_html(audio_files[i]),
                    )

    return demo


if __name__ == "__main__":
    scripts_dir = os.path.realpath(os.path.dirname(__file__))
    gr.set_static_paths([os.path.realpath(tempfile.gettempdir()), scripts_dir])
    app = build_preview()
    app.launch(
        server_port=7870,
        css=CUSTOM_CSS,
        head=HEAD_HTML,
    )
