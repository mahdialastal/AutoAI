# MarkSoft AutoShorts

Turn long videos or YouTube links into short clips (Shorts / Reels / TikTok) using **only local tools**: no cloud APIs, no sign-up.

## What it does

- **Transcribes** the video with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Finds viral moments** with a local LLM via [Ollama](https://ollama.ai)
- **Cuts, crops to 9:16, and burns captions** with [FFmpeg](https://ffmpeg.org)
- **Smart reframe:** face tracking ([MediaPipe](https://mediapipe.dev)), multiple layouts (streaming webcam+chat, split screen, speaker center, event/news), manual crop regions with preview
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

## Web UI

```bash
python app_gradio.py
```

Open the URL shown (e.g. http://127.0.0.1:7860), paste a YouTube URL or upload a video, choose how many shorts to generate, pick a layout, and click **Generate shorts**.

**Where files are saved:** Downloaded videos go to **`downloads/`**, and generated shorts go to **`generated/YYYY-MM-DD_HH-MM-SS/`** (one folder per run).

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

## Features & roadmap

- **Done:** YouTube/local input, transcription, AI highlight selection, 9:16 + layouts (streaming webcam+chat, split, speaker, event/news), face-aware crop, manual crop regions with presets and preview, center fill for gap, burned-in captions.
- **Possible next:** Virality score per clip, auto-trim silences, caption styling, resolution options.

See **[docs/TOOLS_AND_SETUP.md](docs/TOOLS_AND_SETUP.md)** for install notes and pipeline overview.

## License

MIT.
