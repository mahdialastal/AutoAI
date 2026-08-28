"""FastAPI routes for extracting one smart post frame from a source video."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..download import get_video_path
from ..post_frames import extract_best_post_frame


APP_ROOT = Path(__file__).resolve().parents[3]
DOWNLOADS = APP_ROOT / "downloads"
POST_FRAMES = APP_ROOT / "post_frames"

DOWNLOADS.mkdir(parents=True, exist_ok=True)
POST_FRAMES.mkdir(parents=True, exist_ok=True)

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


def _safe_job_id(value: str) -> str:
    value = str(value or "").strip()

    if not re.fullmatch(
        r"frame_[A-Za-z0-9_-]+",
        value,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid frame job id",
        )

    return value


def _job_dir(frame_job_id: str) -> Path:
    safe_job_id = _safe_job_id(
        frame_job_id
    )

    job_dir = (
        POST_FRAMES
        / safe_job_id
    ).resolve()

    try:
        job_dir.relative_to(
            POST_FRAMES.resolve()
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Unsafe frame job path",
        )

    return job_dir


@router.post("/api/post-frame/extract")
def extract_post_frame(
    req: PostFrameRequest,
) -> dict:
    """
    Return ONE good 4:5 or 1:1 frame from the requested video period.

    The endpoint is synchronous because extracting/scoring one still image
    is lightweight compared with full video rendering.

    The extractor samples several frames internally and prefers:
    - visible faces
    - visible/open-looking eyes when detectable
    - sharp frames
    - reasonable exposure

    Only the single best frame is saved and returned.
    """
    if req.end <= req.start:
        raise HTTPException(
            status_code=400,
            detail="end must be greater than start",
        )

    try:
        video_path = get_video_path(
            req.source,
            download_dir=DOWNLOADS,
        )

        result = extract_best_post_frame(
            video_path=video_path,
            output_root=POST_FRAMES,
            start=req.start,
            end=req.end,
            aspect_ratio=req.aspect_ratio,
            sample_count=req.sample_count,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Post frame extraction failed: {exc}",
        ) from exc

    frame_job_id = str(
        result[
            "frame_job_id"
        ]
    )

    source_id = video_path.stem

    return {
        "ok": True,
        "frame_job_id": frame_job_id,
        "source_id": source_id,
        "source_path": str(video_path),
        "timestamp": result["timestamp"],
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
    job_dir = _job_dir(
        frame_job_id
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
    Delete the temporary raw frame after n8n/AI no longer needs it.

    This does NOT delete the downloaded source video.
    Source cleanup remains handled separately by:
        DELETE /api/source/{source_id}
    """
    job_dir = _job_dir(
        frame_job_id
    )

    if not job_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Post frame job not found",
        )

    if not job_dir.is_dir():
        raise HTTPException(
            status_code=500,
            detail="Post frame job path is not a directory",
        )

    shutil.rmtree(
        job_dir
    )

    return {
        "ok": True,
        "frame_job_id": frame_job_id,
        "cleaned": True,
        "cleanup_type": "post_frame_only",
        "removed_source": False,
    }
