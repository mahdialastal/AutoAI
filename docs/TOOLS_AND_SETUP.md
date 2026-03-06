# MarkSoft AutoShorts: Tools Reference

MarkSoft AutoShorts turns long videos into shorts using **only local tools**: transcription, highlight detection, smart cropping, captions, and export. Below is how the pipeline is built.

## Feature → Local tool mapping

| Feature | Tool | Purpose |
|--------|------|---------|
| **Best moments / viral clips** | **Ollama** (e.g. Mistral/Llama) | Score transcript segments for highlight selection |
| **Transcription / subtitles** | **Whisper** or **faster-whisper** | Speech-to-text with timestamps (no API) |
| **YouTube → local video** | **yt-dlp** | Download video/audio from YouTube (or use local file) |
| **Cut, crop, resize, trim** | **FFmpeg** | All editing: trim segments, 9:16 crop, resize, merge |
| **Smart vertical reframing** | **MediaPipe** (optional) | Face/speaker tracking for follow-the-speaker crop |
| **Burned-in captions** | **FFmpeg** + **Whisper** | SRT from Whisper → FFmpeg `-vf subtitles` |
| **Edit short (trim)** | **Ollama** + **FFmpeg** | Natural-language prompt → trim start/end → FFmpeg `-ss` / `-t` |
| **Podcast / long-form transcript** | **Whisper** / **faster-whisper** | Same as above; export transcript only if needed |

## Required tools (install once)

### 1. FFmpeg
- **macOS:** `brew install ffmpeg`
- **Ubuntu/Debian:** `sudo apt install ffmpeg`
- **Windows:** [ffmpeg.org](https://ffmpeg.org/download.html) or `winget install ffmpeg`
- **Burned-in captions:** If you see "No such filter: 'subtitles'", run `brew install libass` then `brew reinstall ffmpeg`. Shorts still generate without captions; SRT files are saved alongside.

### 2. Python 3.11+
- **macOS:** `brew install python@3.11` or use [pyenv](https://github.com/pyenv/pyenv)
- **Ubuntu:** `sudo apt install python3.11 python3.11-venv`

### 3. Ollama (local LLM for highlight detection)
- Install: [ollama.ai](https://ollama.ai)
- After install: `ollama pull mistral` (or `llama3.2`, `phi3`, etc.)

### 4. yt-dlp (if using YouTube URLs)
- `pip install yt-dlp` (included in this project’s `requirements.txt`)

## Python stack (this project)

- **faster-whisper** – fast, local transcription with word-level timestamps
- **yt-dlp** – download YouTube (or local file path)
- **ollama** (Python client) – call local LLM to pick best segments from transcript
- **subprocess** – run FFmpeg for cut/crop/captions
- **mediapipe** (optional) – face detection for smart vertical crop
- **gradio** – web UI

## Pipeline (high level)

```
Input: YouTube URL or local video file
    ↓
yt-dlp → video (or use file)
    ↓
faster-whisper → transcript with timestamps
    ↓
Ollama (LLM) → list of best segments [start, end] (e.g. 15–60 s each)
    ↓
FFmpeg: cut segment → crop to 9:16 (layout: streaming / split / speaker / event) → burn captions
    ↓
Output: Shorts (MP4) in a folder
```

This pipeline runs fully on your machine with no external APIs.
