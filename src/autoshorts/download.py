"""Download video from YouTube URL or return path for local file."""
from __future__ import annotations

import os
from pathlib import Path

import yt_dlp


def get_video_path(source: str, download_dir: Path | None = None) -> Path:
    """
    If source is a URL, download with yt-dlp and return path to video.
    If source is a local path, return it as-is (if file exists).
    download_dir: if set, save downloads here (e.g. app folder); else use system temp.
    """
    source = source.strip()
    if os.path.isfile(source):
        return Path(source).resolve()

    # YouTube or other URL
    if download_dir is not None:
        out_dir = Path(download_dir)
    else:
        import tempfile
        out_dir = Path(tempfile.gettempdir()) / "autoshorts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(out_dir / "%(id)s.%(ext)s")

    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": out_tpl,
        "merge_output_format": "mp4",
        "quiet": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        path = ydl.prepare_filename(info)
        if not path or not os.path.isfile(path):
            # prepare_filename might not include merge suffix
            candidates = list(out_dir.glob(f"{info.get('id', 'unknown')}*.mp4"))
            if candidates:
                return Path(candidates[0])
            raise FileNotFoundError(f"Download failed: {source}")
        return Path(path)
