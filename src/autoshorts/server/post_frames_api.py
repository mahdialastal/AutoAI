"""FastAPI routes for extracting one smart post frame from a partial source clip."""
from __future__ import annotations

import re
import shutil
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

POST_FRAMES.mkdir(parents=True, exist_ok=True)
POST_SOURCES.mkdir(parents=True, exist_ok=True)

router = APIRouter()


class PostFrameRequest(BaseModel):
    """Request one good still frame from a selected story window."""

    source: str = Field(
        ...,
        min_length=1,
        description="YouTube URL or absolute local path to the source video.",
    )

    start: float = Field(
        ...,
        ge=0,
        description="Start time in seconds in the original source video.",
    )

    end: float = Field(
        ...,
        gt=0,
        description="End time in seconds in the original source video.",
    )

    aspect_ratio: Literal[
        "4:5",
        "1:1",
    ] = Field(
        default="4:5",
        description="Target aspect ratio for the Facebook/social post image.",
    )

    sample_count: int = Field(
        default=9,
        ge=5,
        le=15,
        description=(
            "How many frames to inspect internally before returning ONE best frame."
        ),
    )


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


@router.post("/api/post-frame/extract")
def extract_post_frame(
    req: PostFrameRequest,
) -> dict:
    """
    Download ONLY the requested story window, then return ONE best frame.

    Flow:
    1. Create a temporary partial source clip for req.start -> req.end
    2. Sample 5-15 frames inside that short clip
    3. Prefer visible faces, eyes, sharpness and reasonable exposure
    4. Save only ONE 4:5 or 1:1 JPEG

    No polling is needed because this remains much lighter than full Reel render.
    """
    if req.end <= req.start:
        raise HTTPException(
            status_code=400,
            detail="end must be greater than start",
        )

    partial = None

    try:
        partial = download_post_clip(
            source=req.source,
            output_root=POST_SOURCES,
            start=req.start,
            end=req.end,
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

        result = extract_best_post_frame(
            video_path=clip_path,
            output_root=POST_FRAMES,
            start=0.0,
            end=clip_duration,
            aspect_ratio=req.aspect_ratio,
            sample_count=req.sample_count,
        )

    except FileNotFoundError as exc:
        if partial:
            shutil.rmtree(
                partial.get(
                    "source_job_dir",
                    "",
                ),
                ignore_errors=True,
            )

        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        if partial:
            shutil.rmtree(
                partial.get(
                    "source_job_dir",
                    "",
                ),
                ignore_errors=True,
            )

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        if partial:
            shutil.rmtree(
                partial.get(
                    "source_job_dir",
                    "",
                ),
                ignore_errors=True,
            )

        raise HTTPException(
            status_code=500,
            detail=f"Post frame extraction failed: {exc}",
        ) from exc

    frame_job_id = str(
        result[
            "frame_job_id"
        ]
    )

    source_job_id = str(
        partial[
            "source_job_id"
        ]
    )

    # Translate the best-frame timestamp back to original source time.
    original_timestamp = (
        float(req.start)
        + float(
            result[
                "timestamp"
            ]
        )
    )

    return {
        "ok": True,
        "frame_job_id": frame_job_id,
        "source_job_id": source_job_id,
        "partial_source": True,
        "clip_start": partial["clip_start"],
        "clip_end": partial["clip_end"],
        "clip_duration": partial["clip_duration"],
        "timestamp": round(
            original_timestamp,
            3,
        ),
        "local_clip_timestamp": result["timestamp"],
        "face_count": result["face_count"],
        "eye_count": result["eye_count"],
        "blur_variance": result["blur_variance"],
        "brightness": result["brightness"],
        "sampled_frames": result["sampled_frames"],
        "aspect_ratio": result["aspect_ratio"],
        "resolution": result["resolution"],
        "frame_url": (
            f"/api/post-frame/{frame_job_id}/image"
        ),
    }


@router.get("/api/post-frame/{frame_job_id}/image")
def get_post_frame(
    frame_job_id: str,
) -> FileResponse:
    """Return the extracted frame image."""
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
            detail="Post frame not found",
        )

    return FileResponse(
        path=str(frame_path),
        media_type="image/jpeg",
        filename="frame.jpg",
    )


@router.delete("/api/post-frame/{frame_job_id}")
def cleanup_post_frame(
    frame_job_id: str,
) -> dict:
    """
    Delete the raw extracted frame after AI/Drive upload.
    This does NOT delete the partial source clip.
    """
    job_dir = _safe_job_dir(
        POST_FRAMES,
        frame_job_id,
        "frame",
    )

    if not job_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Post frame job not found",
        )

    shutil.rmtree(
        job_dir
    )

    return {
        "ok": True,
        "frame_job_id": frame_job_id,
        "cleaned": True,
        "cleanup_type": "post_frame_only",
        "removed_partial_source": False,
    }


@router.delete("/api/post-source/{source_job_id}")
def cleanup_post_source(
    source_job_id: str,
) -> dict:
    """
    Delete the temporary partial source clip after the final image is safely uploaded.
    """
    job_dir = _safe_job_dir(
        POST_SOURCES,
        source_job_id,
        "postsrc",
    )

    if not job_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Partial post source job not found",
        )

    shutil.rmtree(
        job_dir
    )

    return {
        "ok": True,
        "source_job_id": source_job_id,
        "cleaned": True,
        "cleanup_type": "post_partial_source_only",
    }
