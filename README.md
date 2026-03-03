# AutoShorts — Klap-like shorts generator (runs 100% locally)

Turn long videos or YouTube links into short clips (Shorts / Reels / TikTok) using **only local tools**: no cloud APIs, no sign-up.

**Goal:** Do what these apps do—locally. We’re matching the core workflow of Klap, Opus Clip, Vidyo, Dumme, 2short, Munch, Qlip, Spikes Studio, Vizard, Ssemble, Veed, Submagic, Zubtitle, Wisecut, LiveLink, SendShort, Short.ai, and Nexus Clips (AI highlights, vertical reframe, captions, export), with a clear [feature parity roadmap](docs/FEATURE_PARITY.md) for what’s next.

## Apps we’re matching (cloud versions)

- **Klap**, **2short AI**, **Dumme**, **Munch**, **Opus Clip**, **Qlip**, **Spikes Studio**, **Vidyo**, **Vizard AI**
- **Ssemble**, **Veed.io**, **Submagic**, **Zubtitle**, **Wisecut**
- **LiveLink**, **SendShort**, **Short.ai**, **Nexus Clips**

Use AutoAI when you want the same “long video → viral shorts” pipeline on your own machine.

## What it does today (same idea as [Klap.app](https://klap.app))

- **Transcribes** the video with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Finds viral moments** with a local LLM via [Ollama](https://ollama.ai)
- **Cuts, crops to 9:16, and burns captions** with [FFmpeg](https://ffmpeg.org)
- **Smart reframe:** face tracking ([MediaPipe](https://mediapipe.dev)), multiple layouts (split screen, bottom strip, center), manual crop region (sliders or draw-a-box on preview)
- **Optional:** use a YouTube URL (downloads with [yt-dlp](https://github.com/yt-dlp/yt-dlp))

## Prerequisites (install once)

1. **FFmpeg** — `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)
2. **Python 3.11+**
3. **Ollama** — [ollama.ai](https://ollama.ai), then: `ollama pull mistral`

## Quick start

```bash
# Clone or cd into project
cd AutoAI

# Virtual env and deps
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Generate 3 shorts from a YouTube video
python cli.py "https://youtube.com/watch?v=VIDEO_ID" -o ./my_shorts -n 3

# Or from a local file
python cli.py /path/to/video.mp4 -n 5
```

Output: `./my_shorts/short_1.mp4`, `short_2.mp4`, … (9:16, with burned-in captions).

## Web UI (optional)

```bash
python app_gradio.py
```

Open the URL shown (e.g. http://127.0.0.1:7860), paste a YouTube URL or upload a video, choose how many shorts to generate, and click **Generate shorts**.

**Where files are saved (web app):** Everything stays in the AutoAI folder—no hidden system temp paths. Downloaded videos go to **`AutoAI/downloads/`**, and generated shorts go to **`AutoAI/generated/YYYY-MM-DD_HH-MM-SS/`** (one folder per run so nothing is overwritten).

For the bottom-left-on-top layout, use the video file (or URL), not a full-screen recording.

## CLI options

| Option | Description | Default |
|--------|-------------|--------|
| `source` | YouTube URL or path to video file | — |
| `-o`, `--output-dir` | Output folder | `./shorts_out` |
| `-n`, `--num-clips` | Number of shorts to generate | 3 |
| `--whisper-model` | Whisper size: tiny, base, small, medium, large-v2, large-v3 | base |
| `--ollama-model` | Ollama model for highlight selection | mistral |
| `--chunk-duration` | Chunk length (sec) for LLM | 30 |
| `--min-duration` / `--max-duration` | Clip length range (sec) | 15–60 |
| `--no-captions` | Skip burning captions | off |

When you use a YouTube URL with the CLI, the video is saved to `AutoAI/downloads/`, not system temp.

## Feature parity & roadmap

**[docs/FEATURE_PARITY.md](docs/FEATURE_PARITY.md)** defines what “doing what those apps do” means: a unified feature list (input, transcription, highlight detection, reframing, captions, metadata, export) and a **prioritized roadmap** so AutoAI can match them locally.

- **Done:** YouTube/local input, transcription, AI highlight selection, 9:16 + layouts, face-aware crop, manual crop region, burned-in captions.
- **Next (Phase 1):** Virality score per clip, auto-trim silences, per-clip title/description/hashtags, optional translated captions.
- **Later:** Caption styling, resolution/quality options, optional logo overlay.

## Tools reference

See **[docs/TOOLS_AND_SETUP.md](docs/TOOLS_AND_SETUP.md)** for the full mapping of Klap features to local tools, install notes, and pipeline overview.

## License

MIT.
