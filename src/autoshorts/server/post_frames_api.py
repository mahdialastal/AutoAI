"""FastAPI routes for extracting one smart post frame from a partial source clip."""
from __future__ import annotations

import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..post_frames import (
    download_post_clip,
    extract_best_post_frame,
)


APP_ROOT = Path(__file__).resolve().parents[3]

POST_FRAMES = APP_ROOT / "post_frames"
POST_SOURCES = APP_ROOT / "post_sources"

POST_FRAMES.mkdir(
    parents=True,
    exist_ok=True,
)

POST_SOURCES.mkdir(
    parents=True,
    exist_ok=True,
)

router = APIRouter()


# ============================================================
# POST FRAME REQUEST MODEL
# ============================================================

class PostFrameRequest(BaseModel):
    """Request one good still frame from a selected story window."""

    source: str = Field(
        ...,
        min_length=1,
        description=(
            "YouTube URL or absolute local path "
            "to the source video."
        ),
    )

    start: float = Field(
        ...,
        ge=0,
        description=(
            "Start time in seconds "
            "in the original source video."
        ),
    )

    end: float = Field(
        ...,
        gt=0,
        description=(
            "End time in seconds "
            "in the original source video."
        ),
    )

    aspect_ratio: Literal[
        "4:5",
        "1:1",
    ] = Field(
        default="4:5",
        description=(
            "Target aspect ratio for the "
            "Facebook/social post image."
        ),
    )

    sample_count: int = Field(
        default=9,
        ge=5,
        le=15,
        description=(
            "How many frames to inspect internally "
            "before returning ONE best frame."
        ),
    )


# ============================================================
# ASYNC JOB REGISTRY
# ============================================================

_POST_FRAME_JOBS: dict[str, dict] = {}

_POST_FRAME_JOBS_LOCK = threading.Lock()


def _update_post_frame_job(
    request_id: str,
    **changes,
) -> None:
    """Safely update one post-frame job."""

    with _POST_FRAME_JOBS_LOCK:

        job = _POST_FRAME_JOBS.get(
            request_id
        )

        if job is None:
            return

        job.update(
            changes
        )

        job["updated_at"] = (
            datetime.now().isoformat()
        )


# ============================================================
# SAFE PATH HELPERS
# ============================================================

def _safe_job_id(
    value: str,
    prefix: str,
) -> str:

    value = str(
        value or ""
    ).strip()

    if not re.fullmatch(
        rf"{re.escape(prefix)}_[A-Za-z0-9_-]+",
        value,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid job id",
        )

    return value


def _safe_job_dir(
    root: Path,
    job_id: str,
    prefix: str,
) -> Path:

    safe_job_id = _safe_job_id(
        job_id,
        prefix,
    )

    job_dir = (
        root
        / safe_job_id
    ).resolve()

    try:

        job_dir.relative_to(
            root.resolve()
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Unsafe job path",
        )

    return job_dir


# ============================================================
# BACKGROUND WORKER
# ============================================================

def _run_post_frame_worker(
    request_id: str,
    req: PostFrameRequest,
) -> None:

    partial = None

    try:

        # ----------------------------------------------------
        # DOWNLOAD PARTIAL SOURCE
        # ----------------------------------------------------

        _update_post_frame_job(
            request_id,
            status="running",
            stage="downloading",
            message=(
                "Downloading requested source interval."
            ),
        )

        partial = download_post_clip(
            source=req.source,
            output_root=POST_SOURCES,
            start=req.start,
            end=req.end,
        )

        source_job_id = str(
            partial[
                "source_job_id"
            ]
        )

        clip_path = Path(
            partial[
                "clip_path"
            ]
        )

        clip_duration = float(
            partial[
                "clip_duration"
            ]
        )

        _update_post_frame_job(
            request_id,
            source_job_id=source_job_id,
            clip_start=partial[
                "clip_start"
            ],
            clip_end=partial[
                "clip_end"
            ],
            clip_duration=clip_duration,
            stage="analyzing",
            message=(
                "Analyzing candidate frames."
            ),
        )

        # ----------------------------------------------------
        # FIND BEST FRAME
        # ----------------------------------------------------

        result = extract_best_post_frame(
            video_path=clip_path,
            output_root=POST_FRAMES,
            start=0.0,
            end=clip_duration,
            aspect_ratio=req.aspect_ratio,
            sample_count=req.sample_count,
        )

        frame_job_id = str(
            result[
                "frame_job_id"
            ]
        )

        # Convert local clip timestamp
        # back to original YouTube timestamp.
        original_timestamp = (
            float(req.start)
            + float(
                result[
                    "timestamp"
                ]
            )
        )

        response = {
            "ok": True,

            "request_id": request_id,

            "frame_job_id": (
                frame_job_id
            ),

            "source_job_id": (
                source_job_id
            ),

            "partial_source": True,

            "clip_start": (
                partial[
                    "clip_start"
                ]
            ),

            "clip_end": (
                partial[
                    "clip_end"
                ]
            ),

            "clip_duration": (
                clip_duration
            ),

            "timestamp": round(
                original_timestamp,
                3,
            ),

            "local_clip_timestamp": (
                result[
                    "timestamp"
                ]
            ),

            "face_count": (
                result[
                    "face_count"
                ]
            ),

            "eye_count": (
                result[
                    "eye_count"
                ]
            ),

            "blur_variance": (
                result[
                    "blur_variance"
                ]
            ),

            "brightness": (
                result[
                    "brightness"
                ]
            ),

            "sampled_frames": (
                result[
                    "sampled_frames"
                ]
            ),

            "aspect_ratio": (
                result[
                    "aspect_ratio"
                ]
            ),

            "resolution": (
                result[
                    "resolution"
                ]
            ),

            "frame_url": (
                f"/api/post-frame/"
                f"{frame_job_id}/image"
            ),
        }

        # ----------------------------------------------------
        # DONE
        # ----------------------------------------------------

        _update_post_frame_job(
            request_id,
            status="done",
            stage="done",
            message=(
                "Post frame extracted successfully."
            ),
            result=response,
            error=None,
        )

    except Exception as exc:

        # If download happened but frame extraction failed,
        # remove the temporary partial source.
        if partial:

            source_job_dir = partial.get(
                "source_job_dir"
            )

            if source_job_dir:

                shutil.rmtree(
                    source_job_dir,
                    ignore_errors=True,
                )

        _update_post_frame_job(
            request_id,
            status="failed",
            stage="failed",
            message=(
                "Post frame extraction failed."
            ),
            error=str(exc),
        )


# ============================================================
# START ASYNC EXTRACTION
# ============================================================

@router.post(
    "/api/post-frame/extract",
    status_code=202,
)
def extract_post_frame(
    req: PostFrameRequest,
) -> dict:
    """
    Start post-frame extraction asynchronously.

    Returns immediately with request_id.

    Poll:
        GET /api/post-frame/status/{request_id}

    Possible statuses:
        queued
        running
        done
        failed
    """

    if req.end <= req.start:

        raise HTTPException(
            status_code=400,
            detail=(
                "end must be greater than start"
            ),
        )

    now = datetime.now()

    request_id = now.strftime(
        "postframe_%Y%m%d_%H%M%S_%f"
    )

    created_at = (
        now.isoformat()
    )

    with _POST_FRAME_JOBS_LOCK:

        _POST_FRAME_JOBS[
            request_id
        ] = {

            "ok": True,

            "accepted": True,

            "request_id": (
                request_id
            ),

            "status": "queued",

            "stage": "queued",

            "message": (
                "Post frame request accepted."
            ),

            "created_at": (
                created_at
            ),

            "updated_at": (
                created_at
            ),

            "source": (
                req.source
            ),

            "start": (
                req.start
            ),

            "end": (
                req.end
            ),

            "duration": (
                req.end
                - req.start
            ),

            "aspect_ratio": (
                req.aspect_ratio
            ),

            "sample_count": (
                req.sample_count
            ),

            "source_job_id": None,

            "clip_start": None,

            "clip_end": None,

            "clip_duration": None,

            "result": None,

            "error": None,
        }

    worker = threading.Thread(
        target=_run_post_frame_worker,
        args=(
            request_id,
            req,
        ),
        daemon=True,
    )

    worker.start()

    return {
        "ok": True,

        "accepted": True,

        "request_id": (
            request_id
        ),

        "status": "queued",

        "status_url": (
            f"/api/post-frame/status/"
            f"{request_id}"
        ),
    }


# ============================================================
# STATUS
# ============================================================

@router.get(
    "/api/post-frame/status/{request_id}"
)
def get_post_frame_status(
    request_id: str,
) -> dict:
    """
    Return async post-frame extraction status.

    statuses:
        queued
        running
        done
        failed
    """

    with _POST_FRAME_JOBS_LOCK:

        job = _POST_FRAME_JOBS.get(
            request_id
        )

        if job is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Post frame request not found"
                ),
            )

        return dict(
            job
        )


# ============================================================
# GET IMAGE
# ============================================================

@router.get(
    "/api/post-frame/{frame_job_id}/image"
)
def get_post_frame(
    frame_job_id: str,
) -> FileResponse:

    """Return extracted frame image."""

    job_dir = _safe_job_dir(
        POST_FRAMES,
        frame_job_id,
        "frame",
    )

    frame_path = (
        job_dir
        / "frame.jpg"
    )

    if not frame_path.is_file():

        raise HTTPException(
            status_code=404,
            detail=(
                "Post frame not found"
            ),
        )

    return FileResponse(
        path=str(
            frame_path
        ),
        media_type="image/jpeg",
        filename="frame.jpg",
    )


# ============================================================
# DELETE FRAME
# ============================================================

@router.delete(
    "/api/post-frame/{frame_job_id}"
)
def cleanup_post_frame(
    frame_job_id: str,
) -> dict:

    """
    Delete raw extracted frame.

    Does NOT delete the partial source clip.
    """

    job_dir = _safe_job_dir(
        POST_FRAMES,
        frame_job_id,
        "frame",
    )

    if not job_dir.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "Post frame job not found"
            ),
        )

    shutil.rmtree(
        job_dir
    )

    return {
        "ok": True,

        "frame_job_id": (
            frame_job_id
        ),

        "cleaned": True,

        "cleanup_type": (
            "post_frame_only"
        ),

        "removed_partial_source": (
            False
        ),
    }


# ============================================================
# DELETE PARTIAL SOURCE
# ============================================================

@router.delete(
    "/api/post-source/{source_job_id}"
)
def cleanup_post_source(
    source_job_id: str,
) -> dict:

    """
    Delete temporary partial video source.

    Intended flow:

    Extract frame
    -> AI image
    -> Upload to Drive
    -> delete frame
    -> delete partial source
    """

    job_dir = _safe_job_dir(
        POST_SOURCES,
        source_job_id,
        "postsrc",
    )

    if not job_dir.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "Partial post source job "
                "not found"
            ),
        )

    shutil.rmtree(
        job_dir
    )

    return {
        "ok": True,

        "source_job_id": (
            source_job_id
        ),

        "cleaned": True,

        "cleanup_type": (
            "post_partial_source_only"
        ),
    }
