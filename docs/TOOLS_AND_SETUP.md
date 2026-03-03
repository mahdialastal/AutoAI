# Local Klap-like Stack: Tools Reference

[Klap](https://klap.app) turns long videos into viral shorts with AI: transcription, highlight detection, smart cropping, captions, and export. Below is how to replicate that **fully locally** with open-source tools.

## Klap feature → Local tool mapping

| Klap feature | Local tool | Purpose |
|-------------|------------|--------|
| **Long → short / viral clips** | **Ollama** (e.g. Mistral/Llama) | Score transcript segments for “best moments” / hooks |
| **Transcription / subtitles** | **Whisper** or **faster-whisper** | Speech-to-text with timestamps (no API) |
| **YouTube → local video** | **yt-dlp** | Download video/audio from YouTube (or use local file) |
| **Cut, crop, resize, trim** | **FFmpeg** | All editing: trim segments, 9:16 crop, resize, merge |
| **Smart vertical reframing** | **MediaPipe** (optional) | Face/speaker tracking for follow-the-speaker crop |
| **Burned-in captions** | **FFmpeg** + **Whisper** | SRT from Whisper → `ass`/`srt` → FFmpeg `-vf subtitles` |
| **Podcast / long-form transcript** | **Whisper** / **faster-whisper** | Same as above; export transcript only if needed |
| **(Optional) Translation** | **Ollama** or **argos-translate** | Translate transcript then re-render subtitles |

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

- **faster-whisper** – fast, local transcription with word-level timestamps (or **openai-whisper** if you prefer)
- **yt-dlp** – download YouTube (or local file path)
- **ollama** (Python client) – call local LLM to pick best segments from transcript
- **ffmpeg-python** or **subprocess** – run FFmpeg for cut/crop/captions
- **mediapipe** (optional) – face detection for smart vertical crop
- **gradio** or **streamlit** (optional) – simple web UI

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
FFmpeg: cut segment → crop to 9:16 (center or MediaPipe face track) → burn captions
    ↓
Output: Shorts (MP4) in a folder
```

## Optional: pre-built open-source projects

If you want a ready-made stack instead of this minimal one:

- **[yt-shorts-generator (ShortGen)](https://github.com/Ashwinsuriya/yt-shorts-generator)** – 100% local: Whisper, Ollama, MediaPipe, FFmpeg; CLI + API.
- **[OpenShorts](https://github.com/mutonby/openshorts)** – Web UI, Faster-Whisper, smart crop; uses **Gemini API** for viral-moment detection (not fully local unless you swap in Ollama).

This repo implements a **minimal local pipeline** so you can run everything on your machine with no external APIs.
