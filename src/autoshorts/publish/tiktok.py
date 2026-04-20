"""TikTok Content Posting API uploader.

Default path is *inbox* upload: the video lands in the user's TikTok drafts
and they finalize from the app. This requires only the `video.upload` scope
and works in TikTok Sandbox without production approval.

For direct posting (the `video.publish` scope — requires TikTok review),
pass `direct_post=True`. When direct posting, `privacy_level` is one of
PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, SELF_ONLY.

Setup:
  credentials/tiktok_client.json:
    { "client_key": "...", "client_secret": "...", "redirect_port": 8765 }

On first use a browser window opens for OAuth; the token is cached in
credentials/tiktok_token.json. Add http://localhost:8765/ to your TikTok
app's Redirect URI list.
"""
from __future__ import annotations

import http.server
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

from .base import PublishError, UploadResult
from .credentials import load_json, save_json


AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INBOX_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
DIRECT_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def _client() -> dict:
    try:
        return load_json("tiktok_client.json")
    except FileNotFoundError as e:
        raise PublishError(
            "Missing credentials/tiktok_client.json. Register an app at "
            "https://developers.tiktok.com/, enable Content Posting API, and "
            'save { "client_key": "...", "client_secret": "...", '
            '"redirect_port": 8765 } there.'
        ) from e


def _load_token() -> dict | None:
    try:
        return load_json("tiktok_token.json")
    except FileNotFoundError:
        return None


def _exchange_code_for_token(client: dict, code: str, redirect_uri: str) -> dict:
    r = requests.post(
        TOKEN_URL,
        data={
            "client_key": client["client_key"],
            "client_secret": client["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code != 200:
        raise PublishError(f"TikTok token exchange failed: {r.status_code} {r.text}")
    data = r.json()
    if "access_token" not in data:
        raise PublishError(f"TikTok token response missing access_token: {data}")
    data["expires_at"] = int(time.time()) + int(data.get("expires_in", 3600)) - 60
    return data


def _refresh_token(client: dict, refresh_token: str) -> dict:
    r = requests.post(
        TOKEN_URL,
        data={
            "client_key": client["client_key"],
            "client_secret": client["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if r.status_code != 200:
        raise PublishError(f"TikTok refresh failed: {r.status_code} {r.text}")
    data = r.json()
    data["expires_at"] = int(time.time()) + int(data.get("expires_in", 3600)) - 60
    return data


def _oauth_flow(client: dict, scope: str) -> dict:
    port = int(client.get("redirect_port", 8765))
    redirect_uri = f"http://localhost:{port}/"
    state = secrets.token_urlsafe(16)

    received: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            received.update(params)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h2>TikTok connected.</h2> You can close this tab.")

        def log_message(self, *a, **kw):  # silence
            pass

    server = http.server.HTTPServer(("localhost", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    params = {
        "client_key": client["client_key"],
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    webbrowser.open(f"{AUTH_URL}?{urllib.parse.urlencode(params)}", new=2)

    deadline = time.time() + 300
    while time.time() < deadline and "code" not in received and "error" not in received:
        time.sleep(0.2)
    server.shutdown()

    if "error" in received:
        raise PublishError(f"TikTok OAuth error: {received.get('error_description') or received['error']}")
    if received.get("state") != state:
        raise PublishError("TikTok OAuth state mismatch; possible CSRF. Aborted.")
    if "code" not in received:
        raise PublishError("TikTok OAuth timed out before authorization completed.")
    token = _exchange_code_for_token(client, received["code"], redirect_uri)
    save_json("tiktok_token.json", token)
    return token


def _ensure_token(scope: str) -> str:
    client = _client()
    token = _load_token()
    if token and token.get("expires_at", 0) > time.time() and scope in (token.get("scope") or scope):
        return token["access_token"]
    if token and token.get("refresh_token"):
        try:
            refreshed = _refresh_token(client, token["refresh_token"])
            # Preserve scope hint from prior token if present
            refreshed.setdefault("scope", token.get("scope") or scope)
            save_json("tiktok_token.json", refreshed)
            return refreshed["access_token"]
        except Exception:
            pass
    new = _oauth_flow(client, scope)
    new.setdefault("scope", scope)
    save_json("tiktok_token.json", new)
    return new["access_token"]


def _init_upload(access_token: str, video_size: int, direct_post: bool, post_info: dict | None) -> dict:
    url = DIRECT_INIT_URL if direct_post else INBOX_INIT_URL
    body: dict = {
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        }
    }
    if direct_post and post_info:
        body["post_info"] = post_info
    r = requests.post(
        url,
        json=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=30,
    )
    if r.status_code != 200:
        raise PublishError(f"TikTok init failed: {r.status_code} {r.text}")
    data = r.json().get("data") or {}
    if "upload_url" not in data or "publish_id" not in data:
        raise PublishError(f"TikTok init missing upload_url/publish_id: {r.text}")
    return data


def _upload_file(upload_url: str, video_path: Path) -> None:
    size = video_path.stat().st_size
    with open(video_path, "rb") as f:
        data = f.read()
    r = requests.put(
        upload_url,
        data=data,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{size - 1}/{size}",
        },
        timeout=600,
    )
    if r.status_code not in (200, 201, 204):
        raise PublishError(f"TikTok upload failed: {r.status_code} {r.text}")


def _wait_for_publish(access_token: str, publish_id: str, timeout_sec: float = 180.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        r = requests.post(
            STATUS_URL,
            json={"publish_id": publish_id},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise PublishError(f"TikTok status check failed: {r.status_code} {r.text}")
        data = r.json().get("data") or {}
        status = data.get("status")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            return data
        if status == "FAILED":
            raise PublishError(f"TikTok publish failed: {data.get('fail_reason') or data}")
        time.sleep(3.0)
    raise PublishError(f"TikTok publish timed out after {timeout_sec:.0f}s (publish_id={publish_id})")


def upload_api(
    video_path: str | Path,
    title: str,
    description: str = "",
    *,
    direct_post: bool = False,
    privacy_level: str = "SELF_ONLY",
    disable_duet: bool = False,
    disable_comment: bool = False,
    disable_stitch: bool = False,
    **_ignored,
) -> UploadResult:
    video_path = Path(video_path)
    if not video_path.is_file():
        raise PublishError(f"Video not found: {video_path}")

    scope = "user.info.basic,video.publish" if direct_post else "user.info.basic,video.upload"
    access_token = _ensure_token(scope)

    post_info = None
    if direct_post:
        caption = title if not description else f"{title}\n\n{description}"
        post_info = {
            "title": caption[:2200],
            "privacy_level": privacy_level,
            "disable_duet": disable_duet,
            "disable_comment": disable_comment,
            "disable_stitch": disable_stitch,
        }

    init = _init_upload(access_token, video_path.stat().st_size, direct_post, post_info)
    _upload_file(init["upload_url"], video_path)
    final = _wait_for_publish(access_token, init["publish_id"])

    share_url = final.get("publicaly_available_post_id") or final.get("share_url") or None
    msg = "Posted to TikTok." if direct_post else "Sent to TikTok drafts — finish in the app."
    return UploadResult(
        platform="tiktok", mode="api", ok=True,
        url=share_url, message=msg, remote_id=init["publish_id"],
    )
