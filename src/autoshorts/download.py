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
            info = ydl.extract_info(
                source,
                download=False,
            )

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

    YouTube downloads prefer H.264 / AVC video because OpenCV can
    decode it reliably for Smart Crop and face tracking.

    AV1 is kept only as a fallback when an AVC/H.264 version is
    unavailable.

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

        out_dir = (
            Path(tempfile.gettempdir())
            / "autoshorts"
        )

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    out_tpl = str(
        out_dir / "%(id)s.%(ext)s"
    )

    opts = {
        # -----------------------------------------------------
        # Prefer H.264 / AVC.
        #
        # Smart Crop uses OpenCV to read individual frames.
        # Some OpenCV builds cannot decode YouTube AV1 video,
        # which causes frame_ok=False and therefore zero detected
        # faces.
        #
        # Priority:
        #
        # 1. H.264 MP4 video + M4A audio
        # 2. Combined H.264 MP4 if available
        # 3. Any MP4 video + M4A audio
        # 4. Any MP4
        # 5. Any available format
        # -----------------------------------------------------
        "format": (
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
            "best[vcodec^=avc1][ext=mp4]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "best[ext=mp4]/"
            "best"
        ),

        "outtmpl": out_tpl,

        # Always merge separate video/audio streams to MP4.
        "merge_output_format": "mp4",

        "quiet": False,

        # Enable yt-dlp JavaScript challenge solver components.
        # Deno is installed in the Docker image.
        "remote_components": {
            "ejs:github"
        },
    }

    cookies_file = _get_cookies_file()

    if cookies_file:
        opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(
            source,
            download=True,
        )

        path = ydl.prepare_filename(
            info
        )

        # yt-dlp prepare_filename() may point to the original
        # video-stream filename before FFmpeg merges video/audio.
        if path and os.path.isfile(path):
            return Path(path)

        # Look for the final merged MP4.
        video_id = info.get(
            "id",
            "unknown",
        )

        candidates = list(
            out_dir.glob(
                f"{video_id}*.mp4"
            )
        )

        if candidates:
            return Path(
                candidates[0]
            )

        raise FileNotFoundError(
            f"Download failed: {source}"
        )
