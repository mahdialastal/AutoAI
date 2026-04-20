"""YouTube uploader — thin wrapper around the existing youtube_upload module."""
from __future__ import annotations

from pathlib import Path

from ..youtube_upload import upload_video_to_youtube
from .base import PublishError, UploadResult
from .credentials import credential_file, project_root


def _find_client_secret() -> Path:
    # Back-compat: original location was project root
    legacy = project_root() / "youtube_client_secret.json"
    if legacy.exists():
        return legacy
    return credential_file("youtube_client_secret.json")


def _token_file() -> Path:
    legacy = project_root() / "youtube_token.json"
    if legacy.exists():
        return legacy
    return credential_file("youtube_token.json")


def upload_api(
    video_path: str | Path,
    title: str,
    description: str = "",
    *,
    privacy_status: str = "unlisted",
    **_ignored,
) -> UploadResult:
    client_secret = _find_client_secret()
    if not client_secret.exists():
        raise PublishError(
            f"Missing YouTube OAuth client secret at {client_secret}. "
            "Create one in Google Cloud Console (OAuth client → Desktop app) "
            "and save the JSON there."
        )
    try:
        url = upload_video_to_youtube(
            video_path=video_path,
            title=title,
            description=description,
            privacy_status=privacy_status,
            client_secrets_file=client_secret,
            token_file=_token_file(),
        )
    except Exception as e:
        raise PublishError(f"YouTube upload failed: {e}") from e
    return UploadResult(
        platform="youtube", mode="api", ok=True, url=url,
        message=f"Uploaded as {privacy_status}.",
        remote_id=url.rsplit("=", 1)[-1] if "watch?v=" in (url or "") else None,
    )
