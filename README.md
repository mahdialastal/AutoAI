# MarkSoft AutoShorts

![MarkSoft AutoShorts](autoshorts.png)

Turn long videos — **YouTube**, **Twitch**, **Kick** VODs or your own files — into short-form clips (Shorts / Reels / TikTok) using **only local tools**. No cloud APIs for the pipeline, no sign-up. Publish to YouTube / TikTok / Facebook Reels / Instagram Reels when you're done.

---

## What it does

- **Transcribes** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
- **Finds all good moments** with a local LLM via [Ollama](https://ollama.ai) (no fixed count — as many as the video has).
- **Cuts, crops to 9:16, and burns captions** with [FFmpeg](https://ffmpeg.org).
- **Follows the subject** — per-frame face/person tracking with temporal smoothing ([MediaPipe](https://mediapipe.dev) / YOLOv8), so the 9:16 window pans with the subject instead of sitting on a single static position.
- **Publishes** to YouTube / TikTok / Facebook Reels / Instagram Reels via their APIs, or opens a browser with the file staged if you'd rather finalize by hand.
- **100% local** for generation. Publishing uses the platform APIs only when you explicitly click Publish.

---

## Architecture (2026 rewrite)

Three layers — the pipeline is unchanged, the shell around it is new:

```
┌─────────────────────────────┐
│  web/  React 19 + Vite 6    │     ← user-facing UI
│  + Tailwind 4               │
└──────────────┬──────────────┘
               │ /api/*
┌──────────────┴──────────────┐
│  server.py  FastAPI         │     ← job queue, SSE progress, streaming
│  src/autoshorts/server/     │
└──────────────┬──────────────┘
               │ function calls
┌──────────────┴──────────────┐
│  src/autoshorts/pipeline.py │     ← download → transcribe → highlight
│  + tracking / export /      │       → follow-crop → export → publish
│    publish / ...            │
└─────────────────────────────┘
```

A **legacy Gradio UI** (`app_gradio.py`) is still present during the transition; it will be removed once the React UI reaches feature parity.

---

## Quick start

### Prerequisites (install once)

| Tool | Install |
|------|---------|
| **FFmpeg** | Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to `PATH`. macOS: `brew install ffmpeg`. Linux: `apt install ffmpeg`. |
| **Python 3.11+** | https://www.python.org or `pyenv` / `brew` / `apt`. |
| **Ollama** | https://ollama.ai, then `ollama pull mistral`. |
| **Node 20+** | Only if you want to rebuild the web UI. https://nodejs.org. |

### Run it

```bash
# one-time
python -m venv .venv
.venv\Scripts\activate        # Windows  (or: source .venv/bin/activate on mac/linux)
pip install -r requirements.txt

# start the API + web UI (single process)
python server.py
```

Open **http://localhost:8000**.

If `web/dist/` hasn't been built yet, the root route shows a JSON placeholder telling you to build the frontend — see the next section. The API is live either way at `http://localhost:8000/docs`.

### Build the web UI

```bash
cd web
npm install
npm run build
```

Then re-open `http://localhost:8000`. In dev you can also run `npm run dev` against a live Vite server on `:5173` — it proxies `/api` to FastAPI.

### CLI (for headless runs)

```bash
python cli.py "https://youtube.com/watch?v=VIDEO_ID" -o ./my_shorts -n 10
```

Outputs `my_shorts/short_1.mp4`, …  The CLI path supports the same pipeline but not the publishing step.

### Legacy Gradio UI

Still works during the transition:

```bash
python app_gradio.py
# opens http://127.0.0.1:7860
```

It will be deleted once the React UI hits parity.

---

## How clip selection works

1. **Transcribe** — faster-whisper emits `segments` (phrase-level `start / end / text`).
2. **Select** — Ollama reads the full segment list and returns every moment that would make a good short (hook + payoff, self-contained, duration bounded). There's a user-controlled **cap** but no floor — if the video only has two good moments, you get two.
3. **Align boundaries** —
   - **Start**: walked back to a sentence boundary (capped at 12s) so clips don't start mid-sentence.
   - **End**: extended to the next `.?!` (capped at ~8s of extra content + 3s padding) so punch lines aren't cut off.
4. **Follow** — for single-subject crops, a per-frame face/person tracker builds a time series of subject centers, smoothed with EMA + deadzone + max-speed clamp. The export stage crops the source frame-by-frame so the 9:16 window follows the subject.
5. **Export** — OpenCV pre-renders the cropped frames into an FFmpeg pipe that adds audio from the original and burns captions in one pass.

---

## Publishing

Every generated short can be sent to:

| Platform | API mode | Browser mode |
|---|---|---|
| YouTube | ✅ full (OAuth) | ✅ (opens upload page) |
| TikTok  | ✅ inbox / direct post | ✅ |
| Facebook Reels | ✅ (Page access token) | ✅ |
| Instagram Reels | ✅ (requires public URL host) | mobile only |

See **[docs/PUBLISHING.md](docs/PUBLISHING.md)** for per-platform credential setup.

Credentials live under `credentials/` at the project root. That folder is `.gitignore`d.

---

## Subject follow-tracking

The 9:16 crop pans with the subject automatically. Knobs:

- **Follow mode** — `auto` (face, fall back to person via YOLO), `face`, `person`, `off` (static).
- **Smoothing** — `low` (snappy), `medium` (default), `high` (very smooth, more lag).

Follow is only active for single-window layouts (Speaker, Auto resolving to Speaker). Stacked layouts (streaming, split-screen) use their existing static composition.

Coverage check: if the tracker finds a subject in less than 35 % of sampled frames, the pipeline falls back to the static crop so we don't pan to nothing.

---

## Project layout

```
AutoAI/
├─ server.py                      # uvicorn entry: `python server.py`
├─ cli.py                         # legacy CLI
├─ app_gradio.py                  # legacy Gradio UI (to be removed)
├─ requirements.txt
├─ src/autoshorts/
│  ├─ pipeline.py                 # download → transcribe → select → follow → export
│  ├─ download.py                 # yt-dlp wrapper
│  ├─ transcribe.py               # faster-whisper wrapper
│  ├─ highlights.py               # Ollama: pick moments + write titles
│  ├─ focus.py                    # face detection (legacy static focus)
│  ├─ event_focus.py              # YOLO-based group/event crop
│  ├─ tracking.py                 # NEW: per-frame follow + smoothing
│  ├─ export.py                   # FFmpeg + OpenCV renderer
│  ├─ edit_short.py               # natural-language trim
│  ├─ youtube_upload.py           # legacy YouTube uploader
│  ├─ publish/
│  │  ├─ base.py, credentials.py, assisted.py
│  │  ├─ youtube.py, tiktok.py, facebook.py, instagram.py
│  └─ server/
│     ├─ app.py                   # FastAPI app
│     ├─ jobs.py                  # in-process job registry + SSE
│     └─ models.py                # pydantic req/res models
├─ web/                           # React 19 + Vite 6 + Tailwind 4
│  ├─ src/
│  │  ├─ App.tsx, main.tsx, index.css
│  │  ├─ api/client.ts            # typed fetch + SSE
│  │  └─ components/              # SourceForm, ProgressCard, ShortCard, ShortsGrid, ui
│  ├─ vite.config.ts
│  └─ package.json
├─ docs/
│  ├─ API.md                      # HTTP endpoints
│  ├─ PUBLISHING.md               # per-platform credential setup
│  ├─ FEATURE_PARITY.md
│  └─ TOOLS_AND_SETUP.md
├─ credentials/                   # (git-ignored) OAuth clients + cached tokens
├─ downloads/                     # (git-ignored) yt-dlp output + staged uploads
└─ generated/                     # (git-ignored) <timestamp>/short_N.mp4 + run_metadata.json
```

---

## Roadmap

- **S3** (next): trim + publish wired into the web UI, left-rail run history, credentials UI.
- **S4**: dark-mode polish, keyboard shortcuts, empty/error states, batch publishing.
- **C**: package as a Tauri desktop app.

---

## Troubleshooting

- **"No such filter: 'subtitles'"** — FFmpeg was built without libass. Reinstall FFmpeg with libass support; shorts still render without burned captions as a fallback.
- **Ollama errors** — make sure `ollama serve` is running and you've `ollama pull`ed the model you picked.
- **Cropping wrong** — try turning **Follow** off, or swap layout to **Event** or **Streaming**. For stream layouts, use manual crop regions (in the legacy Gradio UI until the React manual-regions panel lands in S3).
- **Punch line cut off** — pick a larger Whisper model for better sentence punctuation, or raise **Max clip length**.
- **Instagram "cannot reach URL"** — the Graph API fetches your video from a public URL. Host the `generated/` folder somewhere reachable and set `public_base_url` in `credentials/instagram_token.json`. See [docs/PUBLISHING.md](docs/PUBLISHING.md).

---

## License

MIT.
