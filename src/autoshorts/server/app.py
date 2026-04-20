"""FastAPI application for the AutoShorts web UI.

Runs as a single process (`python server.py`). All endpoints are under /api.
When the React build exists at web/dist/ it's served at /.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..pipeline import run_pipeline
from ..publish import publish as publish_dispatch
from .jobs import Job, ProgressEvent, REGISTRY
from .models import (
    JobSummary,
    PresetSummary,
    PublishRequest,
    PublishResponse,
    RunDetail,
    SavePresetRequest,
    ShortInfo,
    StartRunRequest,
)


APP_ROOT = Path(__file__).resolve().parents[3]
GENERATED = APP_ROOT / "generated"
DOWNLOADS = APP_ROOT / "downloads"
PRESETS_FILE = APP_ROOT / "crop_presets.json"
WEB_DIST = APP_ROOT / "web" / "dist"

GENERATED.mkdir(parents=True, exist_ok=True)
DOWNLOADS.mkdir(parents=True, exist_ok=True)


app = FastAPI(title="MarkSoft AutoShorts", version="0.2.0")

# For dev we'll typically run the Vite dev server on :5173 and FastAPI on :8000.
# Same-origin in production (FastAPI serves the built assets).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _job_summary(job: Job) -> JobSummary:
    last = job.events[-1] if job.events else None
    return JobSummary(
        id=job.id,
        run_folder=job.run_folder,
        source=job.source,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        last_stage=last.stage if last else None,
        last_message=last.message if last else None,
        progress=last.progress if last else 0.0,
    )


def _run_pipeline_worker(job: Job, req: StartRunRequest) -> None:
    job.mark_running()
    output_dir = GENERATED / job.run_folder

    def on_progress(stage: str, message: str, progress: float) -> None:
        job.publish(ProgressEvent(ts=time.time(), stage=stage, message=message, progress=progress))

    try:
        paths, titles, full_transcript, short_transcripts = run_pipeline(
            source=req.source,
            output_dir=output_dir,
            download_dir=DOWNLOADS,
            num_clips=req.num_clips,
            whisper_model=req.whisper_model,
            ollama_model=req.ollama_model,
            min_duration=req.min_duration,
            max_duration=req.max_duration,
            burn_captions=req.burn_captions,
            smart_crop=req.smart_crop,
            crop_mode=req.crop_mode,
            focus_region=req.focus_region,
            letterbox_full_width=req.letterbox_full_width,
            manual_webcam_bbox=req.manual_webcam_bbox,
            manual_chat_bbox=req.manual_chat_bbox,
            manual_center_bbox=req.manual_center_bbox,
            follow_mode=req.follow_mode,
            follow_smoothing=req.follow_smoothing,
            on_progress=on_progress,
        )

        shorts = []
        ts_list = short_transcripts or []
        for i, p in enumerate(paths):
            shorts.append({
                "file": p.name,
                "title": titles[i] if i < len(titles) else f"Short {i + 1}",
                "transcript": ts_list[i] if i < len(ts_list) else "",
            })

        try:
            from ..download import get_video_title
            source_label = get_video_title(req.source) or req.source
        except Exception:
            source_label = req.source

        meta = {
            "run_timestamp": job.run_folder.replace("_", " ", 1),
            "source": req.source,
            "source_label": source_label,
            "full_transcript": full_transcript or "",
            "shorts": shorts,
        }
        (output_dir / "run_metadata.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        job.mark_done({"count": len(paths), "run_folder": job.run_folder})
    except Exception as e:
        job.publish(ProgressEvent(ts=time.time(), stage="error", message=str(e), progress=1.0))
        job.mark_failed(str(e))


# ---------- runs ----------

@app.post("/api/runs", response_model=JobSummary)
def start_run(req: StartRunRequest) -> JobSummary:
    run_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    (GENERATED / run_folder).mkdir(parents=True, exist_ok=True)
    job = REGISTRY.create(source=req.source, run_folder=run_folder)
    # Long-running, CPU+GPU bound; run in a daemon thread so the event loop stays free.
    t = threading.Thread(target=_run_pipeline_worker, args=(job, req), daemon=True)
    t.start()
    return _job_summary(job)


@app.get("/api/runs", response_model=list[JobSummary])
def list_jobs() -> list[JobSummary]:
    return [_job_summary(j) for j in REGISTRY.list()]


@app.get("/api/runs/{run_folder}", response_model=RunDetail)
def get_run(run_folder: str) -> RunDetail:
    folder = GENERATED / run_folder
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Run not found")
    meta_path = folder / "run_metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        # Fallback: list mp4s
        meta = {
            "source": "",
            "source_label": run_folder,
            "full_transcript": "",
            "shorts": [
                {"file": p.name, "title": p.stem, "transcript": ""}
                for p in sorted(folder.glob("*.mp4"))
            ],
        }
    shorts = [
        ShortInfo(
            file=s["file"],
            title=s.get("title", s["file"]),
            transcript=s.get("transcript", ""),
            url=f"/api/shorts/{run_folder}/{s['file']}",
        )
        for s in meta.get("shorts", [])
    ]
    return RunDetail(
        run_folder=run_folder,
        source=meta.get("source", ""),
        source_label=meta.get("source_label", ""),
        full_transcript=meta.get("full_transcript", ""),
        shorts=shorts,
    )


@app.get("/api/runs/{run_folder}/progress")
async def run_progress(run_folder: str) -> StreamingResponse:
    """SSE stream of progress events. Replays buffered events on connect."""
    job = REGISTRY.by_run_folder(run_folder)
    if job is None:
        raise HTTPException(status_code=404, detail="No active job for this run")

    queue = job.subscribe()

    async def event_gen():
        try:
            while True:
                if job.status in ("done", "failed", "cancelled") and queue.empty():
                    yield f"event: end\ndata: {json.dumps({'status': job.status, 'error': job.error})}\n\n"
                    return
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = {"stage": ev.stage, "message": ev.message, "progress": ev.progress}
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive so proxies don't close the stream.
                    yield ": keep-alive\n\n"
        finally:
            job.unsubscribe(queue)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---------- shorts ----------

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


@app.get("/api/shorts/{run_folder}/{filename}")
def stream_short(run_folder: str, filename: str, request: Request) -> Response:
    """Byte-range-aware video streaming so the <video> tag can scrub."""
    path = GENERATED / run_folder / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Short not found")
    file_size = path.stat().st_size
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "application/octet-stream"

    range_header = request.headers.get("range") or request.headers.get("Range")
    if not range_header:
        return FileResponse(path, media_type=mime, filename=path.name)

    m = _RANGE_RE.match(range_header)
    if not m:
        raise HTTPException(status_code=416, detail="Bad range")
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else file_size - 1
    end = min(end, file_size - 1)
    if start > end:
        raise HTTPException(status_code=416, detail="Range out of bounds")
    chunk_size = end - start + 1

    def iter_chunk(path: Path, offset: int, length: int, chunk: int = 1 << 16):
        with open(path, "rb") as f:
            f.seek(offset)
            remaining = length
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": mime,
    }
    return StreamingResponse(iter_chunk(path, start, chunk_size), status_code=206, headers=headers)


# ---------- uploads ----------

@app.post("/api/uploads")
async def upload_source(file: UploadFile = File(...)) -> dict:
    """Stage an uploaded source video under downloads/ so a subsequent /api/runs
    call can use it by absolute path."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    stem = Path(file.filename).stem[:40] or "upload"
    ext = Path(file.filename).suffix or ".mp4"
    stable_name = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{stem}{ext}"
    dest = DOWNLOADS / stable_name
    with open(dest, "wb") as out:
        while chunk := await file.read(1 << 20):
            out.write(chunk)
    return {"path": str(dest.resolve()), "name": dest.name}


# ---------- presets ----------

def _load_presets() -> dict:
    if not PRESETS_FILE.exists():
        return {}
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def _save_presets(d: dict) -> None:
    PRESETS_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")


@app.get("/api/presets", response_model=PresetSummary)
def list_presets() -> PresetSummary:
    return PresetSummary(names=sorted(_load_presets().keys()))


@app.get("/api/presets/{name}")
def get_preset(name: str) -> dict:
    data = _load_presets()
    if name not in data:
        raise HTTPException(status_code=404, detail="Preset not found")
    return data[name]


@app.post("/api/presets")
def save_preset(req: SavePresetRequest) -> PresetSummary:
    data = _load_presets()
    data[req.name] = {"webcam": list(req.webcam), "chat": list(req.chat), "center": list(req.center)}
    _save_presets(data)
    return PresetSummary(names=sorted(data.keys()))


@app.delete("/api/presets/{name}")
def delete_preset(name: str) -> PresetSummary:
    data = _load_presets()
    if name in data:
        del data[name]
        _save_presets(data)
    return PresetSummary(names=sorted(data.keys()))


# ---------- publish ----------

@app.post("/api/publish", response_model=PublishResponse)
def publish(req: PublishRequest) -> PublishResponse:
    video_path = GENERATED / req.run_folder / req.file
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail="Short not found")
    opts: dict = {}
    if req.platform == "youtube" and req.privacy_status:
        opts["privacy_status"] = req.privacy_status
    if req.platform == "tiktok":
        opts["direct_post"] = bool(req.tiktok_direct_post)
    try:
        res = publish_dispatch(
            platform=req.platform, mode=req.mode,
            video_path=video_path, title=req.title, description=req.description,
            **opts,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Publish failed: {e}")
    return PublishResponse(
        platform=res.platform, mode=res.mode, ok=res.ok,
        url=res.url, remote_id=res.remote_id, message=res.message,
    )


# ---------- health + static ----------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": app.version, "generated_dir": str(GENERATED)}


# Serve the React build at / when present. During development, run Vite on :5173
# and let CORS handle it; in production run `npm run build` and reload FastAPI.
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
else:
    @app.get("/")
    def root_placeholder() -> JSONResponse:
        return JSONResponse({
            "message": (
                "AutoShorts API is running. The React frontend hasn't been built yet. "
                "During development run `cd web && npm install && npm run dev` and open http://localhost:5173. "
                "For production run `npm run build` — FastAPI will serve web/dist/ from this route."
            ),
            "api_docs": "/docs",
            "health": "/api/health",
        })
