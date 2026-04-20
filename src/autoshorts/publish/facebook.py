"""Facebook Reels uploader (Meta Graph API, resumable upload).

Setup:
  credentials/facebook_token.json:
    {
      "page_id": "<numeric page id>",
      "page_access_token": "<long-lived page access token>",
      "graph_version": "v21.0"         # optional
    }

To get a long-lived page token: create a Meta app, add the Page via Graph API
Explorer, exchange the short-lived user token for a long-lived one, then
GET /me/accounts and pick the page's access_token.
Permissions needed: pages_manage_posts, pages_read_engagement, pages_show_list.
"""
from __future__ import annotations

from pathlib import Path

import requests

from .base import PublishError, UploadResult
from .credentials import load_json


def _cfg() -> dict:
    try:
        return load_json("facebook_token.json")
    except FileNotFoundError as e:
        raise PublishError(
            "Missing credentials/facebook_token.json. See publish/facebook.py "
            "docstring for the required fields."
        ) from e


def _graph_base(cfg: dict) -> str:
    version = cfg.get("graph_version", "v21.0")
    return f"https://graph.facebook.com/{version}"


def _start(cfg: dict) -> dict:
    r = requests.post(
        f"{_graph_base(cfg)}/{cfg['page_id']}/video_reels",
        data={"upload_phase": "start", "access_token": cfg["page_access_token"]},
        timeout=60,
    )
    if r.status_code != 200:
        raise PublishError(f"Facebook reels start failed: {r.status_code} {r.text}")
    data = r.json()
    if "video_id" not in data or "upload_url" not in data:
        raise PublishError(f"Facebook reels start missing fields: {data}")
    return data


def _transfer(upload_url: str, access_token: str, video_path: Path) -> None:
    size = video_path.stat().st_size
    with open(video_path, "rb") as f:
        r = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(size),
            },
            data=f,
            timeout=600,
        )
    if r.status_code != 200:
        raise PublishError(f"Facebook reels transfer failed: {r.status_code} {r.text}")
    body = r.json() if r.content else {}
    if not body.get("success", True):
        raise PublishError(f"Facebook reels transfer not successful: {body}")


def _finish(cfg: dict, video_id: str, caption: str) -> dict:
    r = requests.post(
        f"{_graph_base(cfg)}/{cfg['page_id']}/video_reels",
        params={
            "access_token": cfg["page_access_token"],
            "video_id": video_id,
            "upload_phase": "finish",
            "video_state": "PUBLISHED",
            "description": caption[:2200],
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise PublishError(f"Facebook reels finish failed: {r.status_code} {r.text}")
    return r.json()


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

    started = _start(cfg)
    video_id = started["video_id"]
    _transfer(started["upload_url"], cfg["page_access_token"], video_path)
    _finish(cfg, video_id, caption)

    url = f"https://www.facebook.com/reel/{video_id}"
    return UploadResult(
        platform="facebook", mode="api", ok=True,
        url=url, message="Published to Facebook Reels.", remote_id=video_id,
    )
