"""Browser-assisted publishing. No API keys required.

We open the platform's upload page and stage the video path + caption on the
system clipboard. The user drops the file in and pastes the caption.

Instagram Reels can't be published from a desktop browser in most regions, so
for IG we open the web account page and copy the caption; the user finishes
from their phone.
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

from .base import PublishError, UploadResult

UPLOAD_URLS = {
    "youtube": "https://www.youtube.com/upload",
    "tiktok": "https://www.tiktok.com/upload?lang=en",
    "facebook": "https://www.facebook.com/reels/create",
    "instagram": "https://www.instagram.com/",
}


def _clipboard_write(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def upload_assisted(
    platform: str,
    video_path: str | Path,
    title: str,
    description: str = "",
) -> UploadResult:
    video_path = Path(video_path)
    if not video_path.is_file():
        raise PublishError(f"Video not found: {video_path}")
    if platform not in UPLOAD_URLS:
        raise PublishError(f"No assisted flow for platform: {platform}")

    caption = title if not description else f"{title}\n\n{description}"
    payload = f"{video_path.resolve()}\n\n{caption}"
    clipboard_ok = _clipboard_write(payload)

    url = UPLOAD_URLS[platform]
    webbrowser.open(url, new=2)

    hint = (
        f"Opened {platform} upload page. "
        f"{'File path + caption are on your clipboard — paste the file path into the file picker (Ctrl+L, Ctrl+V) and the caption into the description.' if clipboard_ok else 'Clipboard copy failed; use file: ' + str(video_path.resolve())}"
    )
    if platform == "instagram":
        hint = (
            "Instagram Reels publishing is mobile-only. Opened instagram.com; "
            "caption is on your clipboard. Finish the upload from the Instagram app on your phone."
        )
    return UploadResult(platform=platform, mode="browser", ok=True, url=url, message=hint)
