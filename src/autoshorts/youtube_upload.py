"""Helpers to upload generated shorts directly to YouTube."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Full upload scope so we can create videos
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_credentials(
    client_secrets_file: Path,
    token_file: Path,
) -> Credentials:
    """
    Load or create OAuth credentials for the YouTube Data API.

    On first use, this will open a browser window to let you sign in and
    authorize uploads. The resulting token is saved to token_file so
    subsequent uploads are seamless.
    """
    creds: Optional[Credentials] = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_file), SCOPES
            )
            # Opens a local browser window on first run
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_video_to_youtube(
    video_path: str | Path,
    title: str,
    description: str = "",
    privacy_status: str = "unlisted",
    client_secrets_file: Path | None = None,
    token_file: Path | None = None,
) -> str:
    """
    Upload a single MP4 to YouTube and return the watch URL.

    client_secrets_file: OAuth client JSON from Google Cloud Console.
    token_file: where to cache the user's OAuth token.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if client_secrets_file is None:
        raise ValueError("client_secrets_file is required for YouTube upload.")
    if token_file is None:
        # Store token next to client secrets by default
        token_file = client_secrets_file.with_name("youtube_token.json")

    creds = _get_credentials(client_secrets_file, token_file)

    try:
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description or "",
            },
            "status": {
                "privacyStatus": privacy_status,
            },
        }

        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            # status can be used for progress reporting if desired

        video_id = response.get("id")
        if not video_id:
            raise RuntimeError(f"Upload failed, no video id in response: {response}")
        return f"https://www.youtube.com/watch?v={video_id}"
    except HttpError as e:
        raise RuntimeError(f"YouTube API error: {e}") from e

