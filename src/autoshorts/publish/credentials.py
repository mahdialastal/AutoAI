"""Where platform credentials and cached tokens live.

Users drop their platform-specific credential files under ./credentials/ at
the project root. Tokens obtained via OAuth are cached next to them.

Expected files (user provides the _client files; we write the _token files):
  credentials/youtube_client_secret.json      (also accepted at project root for back-compat)
  credentials/youtube_token.json
  credentials/tiktok_client.json              { "client_key": "...", "client_secret": "..." }
  credentials/tiktok_token.json
  credentials/meta_client.json                { "app_id": "...", "app_secret": "...", "redirect_uri": "http://localhost:<port>/" }
  credentials/facebook_token.json             { "page_id": "...", "page_access_token": "..." }
  credentials/instagram_token.json            { "ig_user_id": "...", "access_token": "...", "public_base_url": "https://..." }
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def creds_dir() -> Path:
    d = project_root() / "credentials"
    d.mkdir(parents=True, exist_ok=True)
    return d


def credential_file(name: str) -> Path:
    return creds_dir() / name


def load_json(name: str) -> dict:
    p = credential_file(name)
    if not p.exists():
        raise FileNotFoundError(f"Missing credentials file: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(name: str, data: dict) -> Path:
    p = credential_file(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return p


def env_or_none(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None
