# AutoShorts HTTP API

FastAPI-based JSON API at `http://localhost:8000/api`. Run with:

```bash
pip install -r requirements.txt
python server.py
```

Interactive docs at `http://localhost:8000/docs` (Swagger UI).

---

## Runs

### `POST /api/runs`
Start a pipeline run. Returns immediately; the work happens in a background thread.

Request body (all fields optional except `source`):

```json
{
  "source": "https://youtube.com/watch?v=...",
  "num_clips": 10,
  "ollama_model": "mistral",
  "whisper_model": "base",
  "min_duration": 15,
  "max_duration": 60,
  "burn_captions": true,
  "smart_crop": true,
  "crop_mode": "auto",
  "focus_region": "full",
  "letterbox_full_width": false,
  "follow_mode": "auto",
  "follow_smoothing": "medium",
  "manual_webcam_bbox": null,
  "manual_chat_bbox": null,
  "manual_center_bbox": null
}
```

Response: a `JobSummary` including `run_folder` (the folder name on disk, e.g. `2026-04-20_15-30-00`).

### `GET /api/runs`
List all jobs (in-memory + filesystem). Most-recent first.

### `GET /api/runs/{run_folder}`
Return a `RunDetail`: source, transcript, list of shorts with URLs.

### `GET /api/runs/{run_folder}/progress`
Server-Sent Events stream. Each event has `stage`, `message`, `progress` (0..1). Stages in order: `download`, `transcribe`, `select`, `titles`, `render`, `done` (or `error`). An `end` event closes the stream.

EventSource example:

```js
const es = new EventSource(`/api/runs/${runFolder}/progress`);
es.onmessage = (e) => { const p = JSON.parse(e.data); /* update UI */ };
es.addEventListener("end", () => es.close());
```

---

## Shorts

### `GET /api/shorts/{run_folder}/{filename}`
Stream an mp4. Supports HTTP Range — safe to use in a `<video>` tag.

---

## Uploads

### `POST /api/uploads`
`multipart/form-data` with field `file`. Stages the file under `downloads/` and returns its absolute path; pass that path as `source` in a subsequent `POST /api/runs`.

---

## Presets (manual crop regions)

- `GET /api/presets` → `{ names: [...] }`
- `GET /api/presets/{name}` → `{ webcam, chat, center }` (each `[l, t, r, b]` in 0..1)
- `POST /api/presets` → save
- `DELETE /api/presets/{name}` → remove

---

## Publishing

### `POST /api/publish`

```json
{
  "run_folder": "2026-04-20_15-30-00",
  "file": "short_1.mp4",
  "title": "...",
  "description": "...",
  "platform": "youtube | tiktok | facebook | instagram",
  "mode": "api | browser",
  "privacy_status": "unlisted",
  "tiktok_direct_post": false
}
```

Credentials live under `credentials/` at the project root. See [PUBLISHING.md](PUBLISHING.md) for per-platform setup.

---

## Health

### `GET /api/health` → `{ ok: true, version: "...", generated_dir: "..." }`

---

## Where files live

```
generated/<run_folder>/
  short_1.mp4
  short_1.srt
  short_N.mp4
  run_metadata.json      # source, transcript, titles, per-short transcripts
downloads/                # staged uploads + yt-dlp output
credentials/              # per-platform OAuth clients + cached tokens
web/dist/                 # (future) React build; served at /
```
