# MarkSoft AutoShorts — Features and roadmap

This document describes what MarkSoft AutoShorts does today and possible next steps.

---

## Current features

### Input & source

| Feature | Status |
|--------|--------|
| YouTube URL | ✅ yt-dlp |
| Local file upload | ✅ CLI + web UI |
| Screen recording / region | ✅ Manual crop, center pre-crop, optional bbox |

### Transcription

| Feature | Status |
|--------|--------|
| Speech-to-text with timestamps | ✅ faster-whisper |
| Auto language detection | ✅ Whisper |

### Highlight / clip detection

| Feature | Status |
|--------|--------|
| Pick N segments from transcript | ✅ Ollama (hooks, punchy, 15–60 s) |

### Vertical reframing & crop

| Feature | Status |
|--------|--------|
| 9:16 vertical export | ✅ |
| Center crop | ✅ |
| Face / speaker tracking | ✅ MediaPipe |
| Layouts: Auto, Streaming (webcam+chat), Split, Speaker, Event/news | ✅ |
| Manual crop regions (webcam, chat, middle) with presets | ✅ |
| Preview regions on frame + preview final 9:16 layout | ✅ |
| Center fill for gap between webcam and chat | ✅ |

### Captions & export

| Feature | Status |
|--------|--------|
| Burned-in subtitles (SRT) | ✅ FFmpeg |
| MP4, 9:16, H.264 | ✅ |

---

## Possible next steps

- **Virality / quality score per clip** — Score each segment (e.g. via LLM), show in UI or use for ordering.
- **Auto-trim silences** — Detect silent stretches and adjust segment boundaries.
- **Per-clip metadata** — Generate title, description, hashtags per short (e.g. next to each MP4).
- **Optional translated captions** — Translate SRT then burn (e.g. Ollama or argos-translate).
- **Caption styling** — Font, size, safe area (e.g. ASS or template).
- **Resolution / quality options** — CLI/UI for output resolution and bitrate.
- **Optional logo overlay** — Logo image + position overlaid via FFmpeg.

MarkSoft AutoShorts runs 100% locally with no external APIs.
