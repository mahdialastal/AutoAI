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
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from yt_dlp import YoutubeDL

from ..pipeline import run_pipeline
from ..download import get_video_path
from ..export import make_short
from ..focus import estimate_focus_x, estimate_focus_track
from ..publish import publish as publish_dispatch
from .jobs import Job, ProgressEvent, REGISTRY
from .models import (
    JobSummary,
    PresetSummary,
    PublishRequest,
    PublishResponse,
    RenderRequest,
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
        job.publish(
            ProgressEvent(
                ts=time.time(),
                stage=stage,
                message=message,
                progress=progress,
            )
        )

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
            shorts.append(
                {
                    "file": p.name,
                    "title": titles[i] if i < len(titles) else f"Short {i + 1}",
                    "transcript": ts_list[i] if i < len(ts_list) else "",
                }
            )

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
            json.dumps(meta, indent=2),
            encoding="utf-8",
        )

        job.mark_done(
            {
                "count": len(paths),
                "run_folder": job.run_folder,
            }
        )

    except Exception as e:
        job.publish(
            ProgressEvent(
                ts=time.time(),
                stage="error",
                message=str(e),
                progress=1.0,
            )
        )
        job.mark_failed(str(e))



# ---------- YouTube transcript (n8n-controlled) ----------

def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm for AI/n8n-friendly transcript text."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def _clean_caption_text(value: str) -> str:
    """Normalize YouTube caption text while preserving the spoken wording."""
    value = value.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", value).strip()


def _language_base(code: str | None) -> str | None:
    """Return the base language code, e.g. en-US -> en, fr-FR -> fr."""
    if not code:
        return None

    normalized = str(code).strip().lower().replace("_", "-")
    if not normalized:
        return None

    return normalized.split("-", 1)[0]


def _language_match(
    detected_language: str | None,
    expected_language: str | None,
) -> bool | None:
    """
    Compare base language codes.

    Returns:
    - True/False when expected_language was supplied
    - None when no expected language was supplied
    """
    expected_base = _language_base(expected_language)
    if expected_base is None:
        return None

    detected_base = _language_base(detected_language)
    if detected_base is None:
        return False

    return detected_base == expected_base


def _parse_json3_transcript(payload: dict) -> list[dict]:
    """
    Convert YouTube json3 captions to normalized transcript segments.

    Returned timestamps are absolute positions in the original source video.
    """
    segments: list[dict] = []

    for event in payload.get("events", []) or []:
        raw_parts = event.get("segs") or []
        if not raw_parts:
            continue

        caption_text = "".join(
            str(part.get("utf8", ""))
            for part in raw_parts
        )
        caption_text = _clean_caption_text(caption_text)

        if not caption_text:
            continue

        start = float(event.get("tStartMs", 0) or 0) / 1000.0
        duration = float(event.get("dDurationMs", 0) or 0) / 1000.0

        segments.append(
            {
                "start": round(start, 3),
                "duration": round(duration, 3),
                "end": round(start + duration, 3),
                "text": caption_text,
            }
        )

    return segments


def _pick_caption_track(
    info: dict,
    requested_language: str | None = None,
) -> tuple[str, str, list[dict]] | None:
    """
    Pick the best available YouTube transcript track.

    Priority:
    1. Human subtitles
    2. Automatic captions

    Within each group:
    - explicitly requested language
    - video's declared language
    - English/French
    - first available language

    Returns: (track_type, language_code, formats)
    """
    requested = (requested_language or "").strip().lower()
    video_language = str(info.get("language") or "").strip().lower()

    groups = (
        ("manual", info.get("subtitles") or {}),
        ("automatic", info.get("automatic_captions") or {}),
    )

    for track_type, tracks in groups:
        if not tracks:
            continue

        available = list(tracks.keys())
        candidates: list[str] = []

        def add_candidate(code: str) -> None:
            if code and code in tracks and code not in candidates:
                candidates.append(code)

        # Exact requested language first.
        add_candidate(requested)

        # Then variants such as en-US for requested "en", or fr-FR for "fr".
        if requested:
            requested_base = requested.split("-", 1)[0]
            for code in available:
                code_lower = code.lower()
                if (
                    code_lower == requested_base
                    or code_lower.startswith(requested_base + "-")
                ):
                    add_candidate(code)

        # Prefer video's own language.
        add_candidate(video_language)
        if video_language:
            video_base = video_language.split("-", 1)[0]
            for code in available:
                code_lower = code.lower()
                if (
                    code_lower == video_base
                    or code_lower.startswith(video_base + "-")
                ):
                    add_candidate(code)

        # Useful defaults for the current France/USA workflow.
        for preferred in ("en", "en-US", "en-GB", "fr", "fr-FR"):
            add_candidate(preferred)

        for code in available:
            add_candidate(code)

        if candidates:
            language_code = candidates[0]
            formats = tracks.get(language_code) or []
            if formats:
                return track_type, language_code, formats

    return None


def _pick_json3_format(formats: list[dict]) -> dict | None:
    """Prefer json3 because it preserves precise segment timestamps."""
    for item in formats:
        if item.get("ext") == "json3" and item.get("url"):
            return item

    return None


def _fetch_youtube_transcript(
    source: str,
    expected_language: str | None = None,
) -> dict:
    """
    Read a transcript directly from YouTube without downloading the video
    and without running Whisper.
    """
    cookie_file = os.getenv("YTDLP_COOKIES_FILE", "").strip()

    ydl_opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "remote_components": {"ejs:github"},
    }

    if cookie_file and Path(cookie_file).is_file():
        ydl_opts["cookiefile"] = cookie_file

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(source, download=False)

    if not info:
        raise RuntimeError("YouTube metadata could not be loaded.")

    video_id = str(info.get("id") or "")
    title = str(info.get("title") or "")
    duration = info.get("duration")

    # Always auto-select the transcript language from YouTube metadata.
    # expected_language is validation-only; it does not force another
    # subtitle track and therefore avoids accidental language conflicts.
    picked = _pick_caption_track(
        info,
        requested_language=None,
    )

    metadata_language = str(info.get("language") or "").strip() or None

    if picked is None:
        return {
            "ok": True,
            "available": False,
            "source": source,
            "video_id": video_id,
            "title": title,
            "duration": duration,
            "language": None,
            "detected_language": metadata_language,
            "expected_language": expected_language,
            "language_match": _language_match(
                metadata_language,
                expected_language,
            ),
            "track_type": None,
            "segments": [],
            "segment_count": 0,
            "full_text": "",
            "timestamped_text": "",
        }

    track_type, language_code, formats = picked

    # Prefer YouTube's declared original video language. If it is missing,
    # fall back to the selected transcript track language.
    detected_language = metadata_language or language_code

    caption_format = _pick_json3_format(formats)

    if caption_format is None:
        # We deliberately require timestamp-rich json3 for this workflow.
        # If YouTube exposes captions but no json3 variant, treat the
        # transcript as unusable instead of inventing/improvising timing.
        return {
            "ok": True,
            "available": False,
            "source": source,
            "video_id": video_id,
            "title": title,
            "duration": duration,
            "language": language_code,
            "detected_language": detected_language,
            "expected_language": expected_language,
            "language_match": _language_match(
                detected_language,
                expected_language,
            ),
            "track_type": track_type,
            "reason": "Transcript exists but no json3 timestamp format is available.",
            "segments": [],
            "segment_count": 0,
            "full_text": "",
            "timestamped_text": "",
        }

    request = urllib.request.Request(
        caption_format["url"],
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()

    payload = json.loads(raw.decode("utf-8"))
    segments = _parse_json3_transcript(payload)

    if not segments:
        return {
            "ok": True,
            "available": False,
            "source": source,
            "video_id": video_id,
            "title": title,
            "duration": duration,
            "language": language_code,
            "detected_language": detected_language,
            "expected_language": expected_language,
            "language_match": _language_match(
                detected_language,
                expected_language,
            ),
            "track_type": track_type,
            "reason": "Caption track was found but contained no usable speech segments.",
            "segments": [],
            "segment_count": 0,
            "full_text": "",
            "timestamped_text": "",
        }

    full_text = "\n".join(
        segment["text"]
        for segment in segments
    )

    timestamped_text = "\n".join(
        f'[{_format_timestamp(segment["start"])}] {segment["text"]}'
        for segment in segments
    )

    return {
        "ok": True,
        "available": True,
        "source": source,
        "video_id": video_id,
        "title": title,
        "duration": duration,
        "language": language_code,
        "detected_language": detected_language,
        "expected_language": expected_language,
        "language_match": _language_match(
            detected_language,
            expected_language,
        ),
        "track_type": track_type,
        "segment_count": len(segments),
        "segments": segments,
        "full_text": full_text,
        "timestamped_text": timestamped_text,
    }


@app.get("/api/transcript")
def youtube_transcript(
    source: str,
    expected_language: str | None = None,
) -> dict:
    """
    Return YouTube transcript + timestamps for n8n.

    Language behavior:
    - Transcript language is selected automatically from YouTube metadata.
    - `expected_language` is optional and validation-only.
    - It never forces another caption track.
    - Response includes detected_language + language_match.

    Examples:
        /api/transcript?source=<youtube_url>
        /api/transcript?source=<youtube_url>&expected_language=en
        /api/transcript?source=<youtube_url>&expected_language=fr

    This endpoint:
    - Does NOT download the source video.
    - Does NOT run Whisper.
    - Uses YouTube human subtitles first, then automatic captions.
    """
    if not source or not source.strip():
        raise HTTPException(
            status_code=422,
            detail="source is required",
        )

    try:
        return _fetch_youtube_transcript(
            source=source.strip(),
            expected_language=expected_language,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not retrieve YouTube transcript: {exc}",
        ) from exc


# ---------- lightweight async render (n8n-controlled) ----------

# In-memory status registry for lightweight render jobs.
#
# The actual rendered file is still written under GENERATED/<run_folder>/.
# The registry only stores small status/result metadata so POST /api/render
# can return immediately instead of waiting for download + tracking + FFmpeg.
#
# This avoids Cloudflare 524 timeouts for long renders.
_RENDER_JOBS: dict[str, dict] = {}
_RENDER_JOBS_LOCK = threading.Lock()


def _update_render_job(render_id: str, **changes) -> None:
    """Safely update one render job's status/result metadata."""
    with _RENDER_JOBS_LOCK:
        job = _RENDER_JOBS.get(render_id)

        if job is None:
            return

        job.update(changes)
        job["updated_at"] = datetime.now().isoformat()


def _run_render_worker(
    render_id: str,
    run_folder: str,
    req: RenderRequest,
) -> None:
    """
    Background worker for /api/render.

    Heavy work happens here:
    - YouTube/local source resolution
    - face tracking
    - dynamic/static vertical crop
    - FFmpeg render

    The HTTP POST has already returned before this starts doing the
    expensive work, so Cloudflare no longer needs to hold the request.
    """
    try:
        _update_render_job(
            render_id,
            status="running",
            stage="downloading",
            message="Downloading or locating source video.",
        )

        video_path = get_video_path(
            req.source,
            download_dir=DOWNLOADS,
        )

        _update_render_job(
            render_id,
            source_path=str(video_path.resolve()),
        )

        output_dir = GENERATED / run_folder
        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = output_dir / "reel.mp4"

        focus_x = None
        focus_track: list[tuple[float, float]] | None = None

        if req.smart_crop and req.crop_mode == "center":
            _update_render_job(
                render_id,
                stage="tracking",
                message="Detecting faces and building dynamic focus track.",
            )

            try:
                focus_track = estimate_focus_track(
                    video_path=video_path,
                    start_sec=req.start,
                    end_sec=req.end,
                    sample_interval=0.5,
                    smoothing=0.35,
                    dead_zone=0.025,
                )
            except Exception:
                focus_track = None

            # Keep the original static Smart Crop as a safe fallback.
            if not focus_track:
                try:
                    focus_x = estimate_focus_x(
                        video_path,
                        req.start,
                        req.end,
                    )
                except Exception:
                    focus_x = None

        _update_render_job(
            render_id,
            stage="rendering",
            message="Rendering 1080x1920 Reel.",
            dynamic_focus=bool(focus_track),
            focus_track_points=len(focus_track) if focus_track else 0,
            focus_x=focus_x,
        )

        make_short(
            video_path=video_path,
            start_sec=req.start,
            end_sec=req.end,
            output_path=output_path,
            srt_path=None,
            width=1080,
            height=1920,
            focus_x=focus_x,
            focus_track=focus_track,
            crop_mode=req.crop_mode,
            focus_region=req.focus_region,
            letterbox_full_width=req.letterbox_full_width,
        )

        if not output_path.is_file():
            raise RuntimeError(
                "Render completed but output file was not created"
            )

        result = {
            "ok": True,
            "render_id": render_id,
            "run_folder": run_folder,
            "file": output_path.name,
            "start": req.start,
            "end": req.end,
            "duration": req.end - req.start,
            "smart_crop": req.smart_crop,
            "dynamic_focus": bool(focus_track),
            "focus_track_points": len(focus_track) if focus_track else 0,
            "focus_x": focus_x,
            "resolution": "1080x1920",
            "url": f"/api/shorts/{run_folder}/{output_path.name}",
        }

        _update_render_job(
            render_id,
            status="done",
            stage="done",
            message="Render completed successfully.",
            result=result,
            error=None,
        )

    except Exception as e:
        _update_render_job(
            render_id,
            status="failed",
            stage="failed",
            message="Render failed.",
            error=str(e),
        )


@app.post("/api/render", status_code=202)
def render_clip(req: RenderRequest) -> dict:
    """
    Start a lightweight video render and return immediately.

    This endpoint is asynchronous from the HTTP client's point of view:
    it creates a background worker and responds with HTTP 202 plus a
    render_id. n8n (or Swagger during testing) can then poll:

        GET /api/render/{render_id}

    until status becomes "done" or "failed".

    This prevents Cloudflare 524 timeouts on long downloads/renders.
    """

    if req.end <= req.start:
        raise HTTPException(
            status_code=400,
            detail="end must be greater than start",
        )

    now = datetime.now()

    render_id = now.strftime(
        "render_%Y%m%d_%H%M%S_%f"
    )

    run_folder = now.strftime(
        "render_%Y-%m-%d_%H-%M-%S-%f"
    )

    created_at = now.isoformat()

    with _RENDER_JOBS_LOCK:
        _RENDER_JOBS[render_id] = {
            "ok": True,
            "render_id": render_id,
            "run_folder": run_folder,
            "status": "queued",
            "stage": "queued",
            "message": "Render job accepted.",
            "created_at": created_at,
            "updated_at": created_at,
            "source": req.source,
            "source_path": None,
            "start": req.start,
            "end": req.end,
            "duration": req.end - req.start,
            "smart_crop": req.smart_crop,
            "dynamic_focus": False,
            "focus_track_points": 0,
            "focus_x": None,
            "result": None,
            "error": None,
        }

    t = threading.Thread(
        target=_run_render_worker,
        args=(
            render_id,
            run_folder,
            req,
        ),
        daemon=True,
    )

    t.start()

    return {
        "ok": True,
        "accepted": True,
        "render_id": render_id,
        "run_folder": run_folder,
        "status": "queued",
        "status_url": f"/api/render/{render_id}",
    }


@app.get("/api/render/{render_id}")
def get_render_status(render_id: str) -> dict:
    """
    Get status/result for a lightweight render job.

    status values:
    - queued
    - running
    - done
    - failed
    """
    with _RENDER_JOBS_LOCK:
        job = _RENDER_JOBS.get(render_id)

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Render job not found",
            )

        # Return a shallow copy so the response is not holding
        # the registry object while FastAPI serializes it.
        return dict(job)




def _cleanup_render_output(render_id: str) -> dict:
    """
    Delete ONLY the generated output for one completed/failed render job.

    Important:
    - Does NOT delete the downloaded YouTube source.
    - Safe to call after n8n uploads the final Reel to Google Drive.
    - Removes the render job from the in-memory registry after cleanup.
    """
    with _RENDER_JOBS_LOCK:
        job = _RENDER_JOBS.get(render_id)

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Render job not found",
            )

        status = job.get("status")

        if status in ("queued", "running"):
            raise HTTPException(
                status_code=409,
                detail="Render job is still running and cannot be cleaned up",
            )

        run_folder = job.get("run_folder")
        source_path_raw = job.get("source_path")

    removed_generated = False

    if run_folder:
        output_dir = (GENERATED / str(run_folder)).resolve()

        try:
            output_dir.relative_to(GENERATED.resolve())
        except ValueError:
            raise HTTPException(
                status_code=500,
                detail="Unsafe generated path detected; cleanup aborted",
            )

        if output_dir.is_dir():
            shutil.rmtree(output_dir)
            removed_generated = True

    # Remove the finished render job entry, but deliberately keep the
    # downloaded source file for the remaining Reels in the source loop.
    with _RENDER_JOBS_LOCK:
        _RENDER_JOBS.pop(render_id, None)

    return {
        "ok": True,
        "render_id": render_id,
        "cleaned": True,
        "cleanup_type": "output_only",
        "removed_generated": removed_generated,
        "removed_source": False,
        "source_preserved": bool(source_path_raw),
    }


@app.delete("/api/render/{render_id}/output")
def cleanup_render_output(render_id: str) -> dict:
    """
    Delete only this Reel's generated output.

    Intended n8n flow for EACH Reel:
        Render -> Download final Reel -> Upload to Google Drive
        -> DELETE /api/render/{render_id}/output

    The long YouTube source remains in /app/downloads for the next Reel.
    """
    return _cleanup_render_output(render_id)


@app.delete("/api/render/{render_id}")
def cleanup_render_legacy(render_id: str) -> dict:
    """
    Backward-compatible cleanup route.

    IMPORTANT:
    This route now behaves as OUTPUT-ONLY cleanup and no longer deletes
    the downloaded source video.

    New workflows should use:
        DELETE /api/render/{render_id}/output
    """
    result = _cleanup_render_output(render_id)
    result["deprecated_route"] = True
    result["recommended_route"] = f"/api/render/{render_id}/output"
    return result


def _validate_source_id(source_id: str) -> str:
    """
    Validate a source identifier before using it to locate temp downloads.

    YouTube video IDs use letters, numbers, '_' and '-'. We allow a slightly
    wider length range so the endpoint remains useful for compatible sources,
    while blocking path traversal and arbitrary filesystem access.
    """
    value = str(source_id or "").strip()

    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", value):
        raise HTTPException(
            status_code=422,
            detail="Invalid source_id",
        )

    return value


@app.delete("/api/source/{source_id}")
def cleanup_source(source_id: str) -> dict:
    """
    Delete the downloaded long-form source AFTER all Reels are complete.

    Intended n8n flow:
        1. Download/use source once
        2. Produce all Reels from the same source
        3. Upload each Reel to Google Drive and clean each output
        4. After the loop finishes:
           DELETE /api/source/{source_id}

    Safety:
    - Only files directly inside DOWNLOADS whose filename stem exactly equals
      source_id are eligible.
    - Refuses deletion while a queued/running render job is using that source.
    """
    safe_source_id = _validate_source_id(source_id)
    downloads_root = DOWNLOADS.resolve()

    candidate_files: list[Path] = []

    if DOWNLOADS.is_dir():
        for candidate in DOWNLOADS.iterdir():
            if not candidate.is_file():
                continue

            resolved = candidate.resolve()

            try:
                resolved.relative_to(downloads_root)
            except ValueError:
                continue

            if candidate.stem == safe_source_id:
                candidate_files.append(resolved)

    # Check active jobs before deleting anything.
    with _RENDER_JOBS_LOCK:
        active_jobs = [
            {
                "render_id": render_id,
                "source_path": str(job.get("source_path") or ""),
            }
            for render_id, job in _RENDER_JOBS.items()
            if job.get("status") in ("queued", "running")
        ]

    candidate_strings = {str(path) for path in candidate_files}
    active_using_source = [
        job["render_id"]
        for job in active_jobs
        if job["source_path"] in candidate_strings
    ]

    if active_using_source:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Source is still being used by an active render job",
                "active_render_ids": active_using_source,
            },
        )

    removed_files: list[str] = []

    for candidate in candidate_files:
        candidate.unlink()
        removed_files.append(candidate.name)

    # Remove any completed/failed registry entries that still reference the
    # source being cleaned. Running/queued jobs were already protected above.
    with _RENDER_JOBS_LOCK:
        stale_render_ids = [
            render_id
            for render_id, job in _RENDER_JOBS.items()
            if (
                job.get("status") not in ("queued", "running")
                and str(job.get("source_path") or "") in candidate_strings
            )
        ]

        for render_id in stale_render_ids:
            _RENDER_JOBS.pop(render_id, None)

    return {
        "ok": True,
        "source_id": safe_source_id,
        "cleaned": True,
        "cleanup_type": "source_only",
        "removed_source": bool(removed_files),
        "removed_files": removed_files,
        "removed_file_count": len(removed_files),
        "active_render_ids": [],
    }


# ---------- runs ----------

@app.post("/api/runs", response_model=JobSummary)
def start_run(req: StartRunRequest) -> JobSummary:
    run_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    (GENERATED / run_folder).mkdir(
        parents=True,
        exist_ok=True,
    )

    job = REGISTRY.create(
        source=req.source,
        run_folder=run_folder,
    )

    # Long-running, CPU+GPU bound; run in a daemon thread
    # so the event loop stays free.
    t = threading.Thread(
        target=_run_pipeline_worker,
        args=(job, req),
        daemon=True,
    )

    t.start()

    return _job_summary(job)


@app.get("/api/runs", response_model=list[JobSummary])
def list_jobs() -> list[JobSummary]:
    return [
        _job_summary(j)
        for j in REGISTRY.list()
    ]


@app.get("/api/runs/{run_folder}", response_model=RunDetail)
def get_run(run_folder: str) -> RunDetail:
    folder = GENERATED / run_folder

    if not folder.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Run not found",
        )

    meta_path = folder / "run_metadata.json"

    if meta_path.exists():
        meta = json.loads(
            meta_path.read_text(
                encoding="utf-8"
            )
        )

    else:
        # Fallback: list mp4s
        meta = {
            "source": "",
            "source_label": run_folder,
            "full_transcript": "",
            "shorts": [
                {
                    "file": p.name,
                    "title": p.stem,
                    "transcript": "",
                }
                for p in sorted(folder.glob("*.mp4"))
            ],
        }

    shorts = [
        ShortInfo(
            file=s["file"],
            title=s.get(
                "title",
                s["file"],
            ),
            transcript=s.get(
                "transcript",
                "",
            ),
            url=f"/api/shorts/{run_folder}/{s['file']}",
        )
        for s in meta.get(
            "shorts",
            [],
        )
    ]

    return RunDetail(
        run_folder=run_folder,
        source=meta.get(
            "source",
            "",
        ),
        source_label=meta.get(
            "source_label",
            "",
        ),
        full_transcript=meta.get(
            "full_transcript",
            "",
        ),
        shorts=shorts,
    )


@app.get("/api/runs/{run_folder}/progress")
async def run_progress(
    run_folder: str
) -> StreamingResponse:
    """
    SSE stream of progress events.

    Replays buffered events on connect.
    """

    job = REGISTRY.by_run_folder(
        run_folder
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="No active job for this run",
        )

    queue = job.subscribe()

    async def event_gen():
        try:
            while True:

                if (
                    job.status
                    in (
                        "done",
                        "failed",
                        "cancelled",
                    )
                    and queue.empty()
                ):
                    yield (
                        "event: end\n"
                        f"data: {json.dumps({'status': job.status, 'error': job.error})}\n\n"
                    )
                    return

                try:
                    ev = await asyncio.wait_for(
                        queue.get(),
                        timeout=15.0,
                    )

                    payload = {
                        "stage": ev.stage,
                        "message": ev.message,
                        "progress": ev.progress,
                    }

                    yield (
                        f"data: {json.dumps(payload)}\n\n"
                    )

                except asyncio.TimeoutError:
                    # Keep-alive so proxies don't close the stream.
                    yield ": keep-alive\n\n"

        finally:
            job.unsubscribe(queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
    )


# ---------- shorts ----------

_RANGE_RE = re.compile(
    r"bytes=(\d+)-(\d*)"
)


@app.get("/api/shorts/{run_folder}/{filename}")
def stream_short(
    run_folder: str,
    filename: str,
    request: Request,
) -> Response:
    """
    Byte-range-aware video streaming
    so the <video> tag can scrub.
    """

    path = (
        GENERATED
        / run_folder
        / filename
    )

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Short not found",
        )

    file_size = path.stat().st_size

    mime, _ = mimetypes.guess_type(
        path.name
    )

    mime = mime or "application/octet-stream"

    range_header = (
        request.headers.get("range")
        or request.headers.get("Range")
    )

    if not range_header:
        return FileResponse(
            path,
            media_type=mime,
            filename=path.name,
        )

    m = _RANGE_RE.match(
        range_header
    )

    if not m:
        raise HTTPException(
            status_code=416,
            detail="Bad range",
        )

    start = int(
        m.group(1)
    )

    end = (
        int(m.group(2))
        if m.group(2)
        else file_size - 1
    )

    end = min(
        end,
        file_size - 1,
    )

    if start > end:
        raise HTTPException(
            status_code=416,
            detail="Range out of bounds",
        )

    chunk_size = (
        end
        - start
        + 1
    )

    def iter_chunk(
        path: Path,
        offset: int,
        length: int,
        chunk: int = 1 << 16,
    ):
        with open(
            path,
            "rb",
        ) as f:

            f.seek(
                offset
            )

            remaining = length

            while remaining > 0:

                data = f.read(
                    min(
                        chunk,
                        remaining,
                    )
                )

                if not data:
                    break

                remaining -= len(
                    data
                )

                yield data

    headers = {
        "Content-Range": (
            f"bytes {start}-{end}/{file_size}"
        ),
        "Accept-Ranges": "bytes",
        "Content-Length": str(
            chunk_size
        ),
        "Content-Type": mime,
    }

    return StreamingResponse(
        iter_chunk(
            path,
            start,
            chunk_size,
        ),
        status_code=206,
        headers=headers,
    )


# ---------- uploads ----------

@app.post("/api/uploads")
async def upload_source(
    file: UploadFile = File(...)
) -> dict:
    """
    Stage an uploaded source video under downloads/
    so a subsequent /api/runs call can use it
    by absolute path.
    """

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No filename",
        )

    stem = (
        Path(file.filename)
        .stem[:40]
        or "upload"
    )

    ext = (
        Path(file.filename)
        .suffix
        or ".mp4"
    )

    stable_name = (
        "upload_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{stem}"
        f"{ext}"
    )

    dest = (
        DOWNLOADS
        / stable_name
    )

    with open(
        dest,
        "wb",
    ) as out:

        while chunk := await file.read(
            1 << 20
        ):
            out.write(
                chunk
            )

    return {
        "path": str(
            dest.resolve()
        ),
        "name": dest.name,
    }


# ---------- presets ----------

def _load_presets() -> dict:
    if not PRESETS_FILE.exists():
        return {}

    return json.loads(
        PRESETS_FILE.read_text(
            encoding="utf-8"
        )
    )


def _save_presets(
    d: dict
) -> None:
    PRESETS_FILE.write_text(
        json.dumps(
            d,
            indent=2,
        ),
        encoding="utf-8",
    )


@app.get(
    "/api/presets",
    response_model=PresetSummary,
)
def list_presets() -> PresetSummary:
    return PresetSummary(
        names=sorted(
            _load_presets().keys()
        )
    )


@app.get("/api/presets/{name}")
def get_preset(
    name: str
) -> dict:

    data = _load_presets()

    if name not in data:
        raise HTTPException(
            status_code=404,
            detail="Preset not found",
        )

    return data[name]


@app.post(
    "/api/presets",
    response_model=PresetSummary,
)
def save_preset(
    req: SavePresetRequest
) -> PresetSummary:

    data = _load_presets()

    data[req.name] = {
        "webcam": list(
            req.webcam
        ),
        "chat": list(
            req.chat
        ),
        "center": list(
            req.center
        ),
    }

    _save_presets(
        data
    )

    return PresetSummary(
        names=sorted(
            data.keys()
        )
    )


@app.delete(
    "/api/presets/{name}",
    response_model=PresetSummary,
)
def delete_preset(
    name: str
) -> PresetSummary:

    data = _load_presets()

    if name in data:
        del data[name]

        _save_presets(
            data
        )

    return PresetSummary(
        names=sorted(
            data.keys()
        )
    )


# ---------- publish ----------

@app.post(
    "/api/publish",
    response_model=PublishResponse,
)
def publish(
    req: PublishRequest
) -> PublishResponse:

    video_path = (
        GENERATED
        / req.run_folder
        / req.file
    )

    if not video_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Short not found",
        )

    opts: dict = {}

    if (
        req.platform == "youtube"
        and req.privacy_status
    ):
        opts["privacy_status"] = (
            req.privacy_status
        )

    if req.platform == "tiktok":
        opts["direct_post"] = bool(
            req.tiktok_direct_post
        )

    try:
        res = publish_dispatch(
            platform=req.platform,
            mode=req.mode,
            video_path=video_path,
            title=req.title,
            description=req.description,
            **opts,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Publish failed: {e}",
        )

    return PublishResponse(
        platform=res.platform,
        mode=res.mode,
        ok=res.ok,
        url=res.url,
        remote_id=res.remote_id,
        message=res.message,
    )


# ---------- health + static ----------

@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": app.version,
        "generated_dir": str(
            GENERATED
        ),
    }


# Serve the React build at / when present.
# During development, run Vite on :5173
# and let CORS handle it.
# In production run npm run build and reload FastAPI.

if WEB_DIST.is_dir():

    app.mount(
        "/",
        StaticFiles(
            directory=str(
                WEB_DIST
            ),
            html=True,
        ),
        name="web",
    )

else:

    @app.get("/")
    def root_placeholder() -> JSONResponse:
        return JSONResponse(
            {
                "message": (
                    "AutoShorts API is running. "
                    "The React frontend hasn't been built yet. "
                    "During development run "
                    "`cd web && npm install && npm run dev` "
                    "and open http://localhost:5173. "
                    "For production run `npm run build` — "
                    "FastAPI will serve web/dist/ from this route."
                ),
                "api_docs": "/docs",
                "health": "/api/health",
            }
        )
