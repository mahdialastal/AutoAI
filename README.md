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

## How clip selection works (workflow)

The app uses **transcript + AI** to decide what to clip. Clips are aligned to **fixed-length chunks**, so punch lines near a chunk boundary can sometimes be cut. Here’s the full flow and how we reduce that.

**1. Transcribe the video**  
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) turns speech into **segments**: short phrases with start/end times (e.g. “So then he said…” from 12.3s to 14.1s). No AI yet — just speech-to-text.

**2. Build chunks**  
Segments are grouped into **chunks** of roughly **30 seconds** (configurable via `--chunk-duration`). Each chunk has one start time, one end time, and the combined text. Boundaries are **time-based**, not “per sentence,” so a punch line that crosses 30s might sit on a chunk edge.

**3. AI picks the best chunks**  
Your local LLM ([Ollama](https://ollama.ai), e.g. Mistral) sees the list of chunks (timestamps + first 200 characters of text) and is asked: *“Which N chunks would make the best viral shorts?”* It prefers strong hooks, clear ideas, and punchy moments. It returns **chunk indices** (e.g. [2, 5, 7]). Those chunks become your N shorts.

**4. Clip boundaries and punch-line safeguard**  
Each short is cut at the chunk’s **start** and **end**. To avoid cutting off the very end of a line (e.g. the punch line), the pipeline **adds a few seconds** after each chunk end (default **5 seconds**), capped at the video length. So a chunk that originally ended at 30s is exported as 30s–35s (or to the end of the video). You can tune this later via a CLI/UI option if needed.

**5. Export**  
For each selected chunk (with the padded end), the app cuts the video, applies your layout (crop/reframe), burns captions, and saves a 9:16 MP4.

**Summary**

| Step | What happens |
|------|----------------------|
| 1. Transcribe | Whisper → segments (phrase-level start/end + text) |
| 2. Chunk | Group segments into ~30s chunks (time-based boundaries) |
| 3. Select | Ollama picks N “best for shorts” chunks from the transcript |
| 4. Pad ends | Add a few seconds after each chunk end (punch-line safeguard) |
| 5. Export | Cut video, crop to layout, burn captions → short |

So: **yes, the AI uses a transcript and analyzes it** — it doesn’t watch the video, only the chunked text and timestamps. If a clip still cuts off a punch line, the line may be right at the end of the padded window; increasing chunk duration or adding a “clip end padding” option later can help.

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
- **Punch line or end of clip is cut off** — Clips are based on fixed-length chunks (see [How clip selection works](#how-clip-selection-works-workflow)). We add 5 seconds after each chunk end to reduce this. If it still happens, the line may be beyond that; try a larger Whisper model or a longer `--chunk-duration` (CLI) so chunks align better with sentences.

---

## License

MIT.
