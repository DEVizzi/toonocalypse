"""YouTube OAuth2 in-memory access-token refresh and health check (§13)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.common.state import load_state, save_state

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def get_youtube_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def build_youtube_client():
    return build("youtube", "v3", credentials=get_youtube_credentials())


def check_youtube_token() -> dict[str, Any]:
    state = load_state("tokens.json", {"youtube": {}, "instagram": {}})
    now = datetime.now(timezone.utc).isoformat()
    try:
        yt = build_youtube_client()
        resp = yt.channels().list(part="id,snippet", mine=True).execute()
        items = resp.get("items", [])
        channel_id = items[0]["id"] if items else None
        state["youtube"] = {"status": "valid", "channel_id": channel_id, "last_checked": now, "last_error": None}
    except Exception as exc:
        state["youtube"] = {"status": "invalid", "last_checked": now, "last_error": type(exc).__name__}
    save_state("tokens.json", state)
    return state["youtube"]
