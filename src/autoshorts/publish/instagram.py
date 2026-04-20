"""Instagram Reels uploader (Meta Graph API, container + publish).

Instagram's Graph API requires the video to be fetched from a public URL, so
you must host generated shorts somewhere the internet can GET them. Options:
 - Put the 'generated/' folder behind an S3/Cloudflare R2/Backblaze bucket
   with public read.
 - Run `cloudflared tunnel` or `ngrok http` against a tiny local HTTP server
   that serves the generated/ directory.

Setup:
  credentials/instagram_token.json:
    {
      "ig_user_id": "<numeric IG Business/Creator account id>",
      "access_token": "<long-lived user access token with instagram_content_publish>",
      "public_base_url": "https://your.host.example.com/shorts/",
      "graph_version": "v21.0"
    }

The uploader treats `public_base_url + <video filename>` as the video URL it
tells Instagram to fetch. The file must already be reachable at that URL when
you click Upload.
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from .base import PublishError, UploadResult
from .credentials import load_json


def _cfg() -> dict:
    try:
        return load_json("instagram_token.json")
    except FileNotFoundError as e:
        raise PublishError(
            "Missing credentials/instagram_token.json. See publish/instagram.py "
            "docstring for the required fields."
        ) from e


def _graph_base(cfg: dict) -> str:
    version = cfg.get("graph_version", "v21.0")
    return f"https://graph.facebook.com/{version}"


def _public_url_for(cfg: dict, video_path: Path) -> str:
    base = cfg.get("public_base_url")
    if not base:
        raise PublishError(
            "public_base_url is required in credentials/instagram_token.json "
            "(Instagram fetches the video from a public URL)."
        )
    if not base.endswith("/"):
        base = base + "/"
    return base + video_path.name


def _create_container(cfg: dict, video_url: str, caption: str) -> str:
    r = requests.post(
        f"{_graph_base(cfg)}/{cfg['ig_user_id']}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "access_token": cfg["access_token"],
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise PublishError(f"Instagram create container failed: {r.status_code} {r.text}")
    data = r.json()
    cid = data.get("id")
    if not cid:
        raise PublishError(f"Instagram create response missing id: {data}")
    return cid


def _wait_container_ready(cfg: dict, creation_id: str, timeout_sec: float = 300.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = requests.get(
            f"{_graph_base(cfg)}/{creation_id}",
            params={"fields": "status_code,status", "access_token": cfg["access_token"]},
            timeout=30,
        )
        if r.status_code != 200:
            raise PublishError(f"Instagram status check failed: {r.status_code} {r.text}")
        data = r.json()
        code = data.get("status_code") or ""
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram container failed: {data}")
        time.sleep(5.0)
    raise PublishError(f"Instagram container not FINISHED within {timeout_sec:.0f}s")


def _publish(cfg: dict, creation_id: str) -> str:
    r = requests.post(
        f"{_graph_base(cfg)}/{cfg['ig_user_id']}/media_publish",
        data={"creation_id": creation_id, "access_token": cfg["access_token"]},
        timeout=60,
    )
    if r.status_code != 200:
        raise PublishError(f"Instagram publish failed: {r.status_code} {r.text}")
    return r.json().get("id", "")


def upload_api(
    video_path: str | Path,
    title: str,
    description: str = "",
    **_ignored,
) -> UploadResult:
    video_path = Path(video_path)
    if not video_path.is_file():
        raise PublishError(f"Video not found: {video_path}")

    cfg = _cfg()
    caption = title if not description else f"{title}\n\n{description}"
    video_url = _public_url_for(cfg, video_path)

    # Quick pre-check: the URL should be reachable before we ask IG to fetch it.
    try:
        head = requests.head(video_url, timeout=10, allow_redirects=True)
        if head.status_code >= 400:
            raise PublishError(
                f"Instagram public_base_url is not serving the file: "
                f"{video_url} returned {head.status_code}. Host the file there first."
            )
    except requests.RequestException as e:
        raise PublishError(f"Cannot reach {video_url}: {e}") from e

    creation_id = _create_container(cfg, video_url, caption)
    _wait_container_ready(cfg, creation_id)
    media_id = _publish(cfg, creation_id)

    url = f"https://www.instagram.com/reel/{media_id}/" if media_id else None
    return UploadResult(
        platform="instagram", mode="api", ok=True,
        url=url, message="Published to Instagram Reels.", remote_id=media_id,
    )
