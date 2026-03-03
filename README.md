# MarkSoft AutoShorts

![MarkSoft AutoShorts](autoshorts.png)

Turn long videos or YouTube links into short clips (Shorts / Reels / TikTok) using **only local tools**: no cloud APIs, no sign-up. All processing runs on your machine.

---

## What it does

- **Transcribes** the video with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Finds viral moments** with a local LLM via [Ollama](https://ollama.ai)
- **Cuts, crops to 9:16, and burns captions** with [FFmpeg](https://ffmpeg.org)
- **Smart reframe:** face tracking ([MediaPipe](https://mediapipe.dev)), multiple layouts (streaming webcam+chat, split screen, speaker center, event/news), manual crop regions with preview and presets
- **Optional:** use a YouTube URL (downloads with [yt-dlp](https://github.com/yt-dlp/yt-dlp))

---

## Prerequisites (install once)

| Tool | Install |
|------|--------|
| **FFmpeg** | `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux). For burned-in captions: `brew install libass` then `brew reinstall ffmpeg` if you see "No such filter: 'subtitles'". |
| **Python 3.11+** | `brew install python@3.11` or [pyenv](https://github.com/pyenv/pyenv) (macOS); `apt install python3.11 python3.11-venv` (Linux). |
| **Ollama** | [ollama.ai](https://ollama.ai), then run: `ollama pull mistral` |

---

## Quick start

```bash
cd AutoAI
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**CLI — generate 3 shorts from a YouTube video:**

```bash
python cli.py "https://youtube.com/watch?v=VIDEO_ID" -o ./my_shorts -n 3
```

**CLI — from a local file:**

```bash
python cli.py /path/to/video.mp4 -n 5
```

Output: `./my_shorts/short_1.mp4`, `short_2.mp4`, … (9:16, with burned-in captions).

**Web UI:**

```bash
python app_gradio.py
```

Open the URL shown (e.g. http://127.0.0.1:7860).

---

## Everything to know

### 1. Input

- **YouTube URL** — Paste a link; the app downloads the video with yt-dlp (saved to `downloads/`).
- **Upload video** — Use a local file instead. No upload to any server; the file is read from your machine.

### 2. Number of shorts

Choose how many clips to generate (1–10). The app picks that many “best moments” from the transcript using the local LLM (Ollama).

### 3. Layout

How the video is cropped and arranged for vertical 9:16:

| Layout | Use when |
|--------|----------|
| **Auto** | Let the app detect: if it sees a face in the left half → Streaming; otherwise → Speaker only or Event. |
| **Event / news** | Chaotic or multi-person footage (e.g. events, news, rescue). Tracks people and crops to keep action in frame. |
| **Streaming (webcam top, chat bottom)** | A stream with webcam + chat on screen. App tries to find the webcam (face) and chat area; use **Set crop regions yourself** if it’s wrong. |
| **Streaming (webcam bottom-left, chat bottom-right)** | Same idea but for layouts where webcam and chat are in the **bottom** of the frame (fixed regions, no detection). |
| **Speaker only** | Single talking head; keeps the face centered. |
| **Split screen** | Splits the frame (bottom-left and bottom-right) and stacks them vertically. |

### 4. Source

- **Full frame** — Use the whole video frame as-is.
- **Screen recording (crop to center)** — For a recording of a browser/app where the real content is in the middle. The app crops to the center 70%×90% first, then applies the layout.

### 5. Output

- **Fill frame (crop to 9:16)** — Scale to fill the vertical frame and center-crop; no black bars.
- **Full width (letterbox)** — Keep the full width of the video and add black bars top/bottom so nothing is cropped horizontally.

### 6. Set crop regions yourself (Streaming only)

When you pick a **Streaming** layout, you can open **“I'll select the webcam and chat areas myself”** and:

- **Use my crop regions** — Turn off auto-detect; the app uses your numbers only.
- **Webcam / Chat / Middle** — Three columns with **Left %, Top %, Right %, Bottom %** (0–100). Same idea for all three: you define a rectangle on the full video. **Webcam** = top of the short, **Chat** = bottom, **Middle** = the strip between them (gap fill). Default for Middle is 25–75 (center of the frame).
- **Saved presets** — Load, save, rename, or delete presets so you don’t re-enter values every time.
- **Preview regions on a frame** — Draws green (webcam), orange (chat), and blue (middle) boxes on a frame so you can check before generating.
- **Preview final layout (9:16)** — Shows exactly how the short will look: webcam on top, middle in the center (if there’s a gap), chat on bottom.

### 7. Generate

Click **Generate shorts**. The app will:

1. Download the video (if URL) or use your file.
2. Transcribe with Whisper.
3. Ask Ollama for the best N segments.
4. For each segment: cut, apply the chosen layout (and your crop regions if set), burn captions, save as 9:16 MP4.

**Where files go:**

- **Downloads:** `downloads/` (YouTube videos).
- **Generated shorts:** `generated/YYYY-MM-DD_HH-MM-SS/` (one folder per run; e.g. `short_1.mp4`, `short_2.mp4`).

---

## CLI reference

| Option | Description | Default |
|--------|-------------|--------|
| `source` | YouTube URL or path to video file | — |
| `-o`, `--output-dir` | Output folder for shorts | `./shorts_out` |
| `-n`, `--num-clips` | Number of shorts to generate | 3 |
| `--whisper-model` | Whisper size: tiny, base, small, medium, large-v2, large-v3 | base |
| `--ollama-model` | Ollama model for highlight selection | mistral |
| `--chunk-duration` | Chunk length (sec) for LLM | 30 |
| `--min-duration` / `--max-duration` | Clip length range (sec) | 15–60 |
| `--no-captions` | Skip burning captions | off |

Example with more clips and a custom output folder:

```bash
python cli.py "https://youtube.com/watch?v=VIDEO_ID" -o ./my_shorts -n 5
```

---

## Features (current)

- YouTube URL + local file input  
- Transcription (faster-whisper), AI highlight selection (Ollama)  
- Layouts: Auto, Event/news, Streaming (two variants), Speaker only, Split screen  
- Full frame vs screen recording (crop to center)  
- Fill frame vs full-width letterbox output  
- Manual crop regions for webcam, chat, and middle (gap fill) with presets  
- Preview regions on a frame + preview final 9:16 layout  
- Burned-in captions (SRT → FFmpeg)  
- 9:16 MP4 (H.264), 100% local

See **[docs/FEATURE_PARITY.md](docs/FEATURE_PARITY.md)** for the full feature list and possible roadmap.  
See **[docs/TOOLS_AND_SETUP.md](docs/TOOLS_AND_SETUP.md)** for tools (FFmpeg, Whisper, Ollama, yt-dlp) and pipeline overview.

---

## Troubleshooting

- **“No such filter: 'subtitles'”** — Install libass and rebuild FFmpeg: `brew install libass` then `brew reinstall ffmpeg`. Shorts still generate; captions are skipped and SRT files are saved.
- **Ollama errors** — Ensure Ollama is running and you’ve run `ollama pull mistral` (or the model you use).
- **Cropping wrong for streaming** — Use **Set crop regions yourself**, enter Left/Top/Right/Bottom % for webcam and chat, enable **Use my crop regions**, then **Preview regions on a frame** to confirm before generating.
- **Middle part looks off** — Adjust the **Middle** column (Left/Top/Right/Bottom %). Lower **Top %** to include more above the subject; use **Preview final layout (9:16)** to check.

---

## License

MIT.
