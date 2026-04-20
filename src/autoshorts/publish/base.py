"""Shared types and error classes for the publish subpackage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Platform = Literal["youtube", "tiktok", "facebook", "instagram"]
PublishMode = Literal["api", "browser"]


class PublishError(RuntimeError):
    """Any failure during publishing — auth, upload, or finalize."""


@dataclass
class UploadResult:
    platform: Platform
    mode: PublishMode
    ok: bool
    url: str | None = None        # canonical watch URL when known
    message: str = ""             # human-readable status
    remote_id: str | None = None  # platform's internal id (video_id / creation_id)
