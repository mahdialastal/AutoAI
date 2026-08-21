"""Download video from YouTube URL or return path for local file."""
from __future__ import annotations

import os
from pathlib import Path

import yt_dlp


def _get_cookies_file() -> str | None:
    """
    Return the configured yt-dlp cookies file if it exists.
    """
    cookies_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()

    if cookies_file and os.path.isfile(cookies_file):
        return cookies_file

    return None


def get_video_title(source: str) -> str | None:
    """
    For YouTube (or other) URLs, return the video title without downloading.
    For local paths, return None.
    """
    source = (source or "").strip()

    if not source.startswith(("http://", "https://")):
        return None

    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "remote_components": {"ejs:github"},
        }

        cookies_file = _get_cookies_file()
        if cookies_file:
            opts["cookiefile"] = cookies_file

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source, download=False)
            return (info or {}).get("title")

    except Exception:
        return None


def get_video_path(
    source: str,
    download_dir: Path | None = None,
) -> Path:
    """
    If source is a URL, download with yt-dlp and return path to video.
    If source is a local path, return it as-is if it exists.

    download_dir:
        If set, save downloads here.
        Otherwise use the system temp directory.
    """
    source = source.strip()

    if os.path.isfile(source):
        return Path(source).resolve()

    if download_dir is not None:
        out_dir = Path(download_dir)
    else:
        import tempfile
        out_dir = Path(tempfile.gettempdir()) / "autoshorts"

    out_dir.mkdir(parents=True, exist_ok=True)

    out_tpl = str(out_dir / "%(id)s.%(ext)s")

    opts = {
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "best[ext=mp4]/best"
        ),
        "outtmpl": out_tpl,
        "merge_output_format": "mp4",
        "quiet": False,

        # Enable yt-dlp JavaScript challenge solver components.
        # Deno is already installed in the Docker image.
        "remote_components": {"ejs:github"},
    }

    cookies_file = _get_cookies_file()

    if cookies_file:
        opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            source,
            download=True,
        )

        path = ydl.prepare_filename(info)

        if path and os.path.isfile(path):
            return Path(path)

        # yt-dlp may merge video/audio into a final MP4 whose
        # filename differs from prepare_filename().
        candidates = list(
            out_dir.glob(
                f"{info.get('id', 'unknown')}*.mp4"
            )
        )

        if candidates:
            return Path(candidates[0])

        raise FileNotFoundError(
            f"Download failed: {source}"
        )
