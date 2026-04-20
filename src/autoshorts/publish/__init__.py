"""Multi-platform publishing for generated shorts.

Each platform exposes two entry points:
  - upload_api(video, title, description, **opts) -> UploadResult
      Programmatic upload via the platform's API. Requires credentials.
  - upload_assisted(video, title, description) -> UploadResult
      Opens the platform's upload page in the browser and puts the file path
      and caption on the clipboard so the user drops them in.

Supported platforms: youtube, tiktok, facebook, instagram.
"""
from __future__ import annotations

from .base import UploadResult, PublishError, Platform, PublishMode
from . import assisted, facebook, instagram, tiktok, youtube

UPLOADERS = {
    "youtube": youtube,
    "tiktok": tiktok,
    "facebook": facebook,
    "instagram": instagram,
}


def publish(
    platform: Platform,
    mode: PublishMode,
    video_path,
    title: str,
    description: str = "",
    **opts,
) -> UploadResult:
    """Dispatch to the right uploader module.

    `platform` selects the target; `mode` picks API vs assisted-browser.
    Platform-specific options go in **opts (e.g. privacy_status for YouTube,
    page_id for Facebook, ig_user_id + public_url for Instagram, etc.).
    """
    if platform not in UPLOADERS:
        raise PublishError(f"Unknown platform: {platform}")
    mod = UPLOADERS[platform]
    if mode == "api":
        return mod.upload_api(video_path, title, description, **opts)
    if mode == "browser":
        return assisted.upload_assisted(platform, video_path, title, description)
    raise PublishError(f"Unknown mode: {mode}")


__all__ = [
    "UploadResult",
    "PublishError",
    "Platform",
    "PublishMode",
    "UPLOADERS",
    "publish",
    "assisted",
]
