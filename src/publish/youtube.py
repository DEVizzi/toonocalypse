"""YouTube Shorts uploader (v4.3.1). Resumable `videos.insert` over HTTPS using the refreshed OAuth access token.

Only invoked by `src.main --publish` AFTER the ffprobe gate passes; never in --dry-run.
Security: token only in the Authorization header; metadata is built from our own league data (no user input);
errors are logged generically (no tokens / response bodies with credentials).
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

from src.publish.oauth import OAuthError, access_token

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
MAX_BYTES = 256 * 1024 * 1024          # Shorts are ~10-20 MB; refuse anything absurd
PRIVACY = ("public", "unlisted", "private")


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).replace("<", "").replace(">", "").split())      # YouTube rejects angle brackets
    return s[:n]


def upload_short(mp4: Path, title: str, description: str, tags: list[str], privacy: str = "public") -> str:
    """Uploads `mp4` and returns the new video id. Raises OAuthError / RuntimeError on failure."""
    if privacy not in PRIVACY:
        raise ValueError("invalid privacy status")
    size = mp4.stat().st_size
    if not (0 < size <= MAX_BYTES):
        raise RuntimeError("video size out of bounds")
    token, _, _ = access_token()
    meta = {
        "snippet": {
            "title": _clip(title, 100),
            "description": _clip(description, 4800),
            "tags": [_clip(t, 30) for t in tags][:15],
            "categoryId": os.environ.get("YT_CATEGORY_ID", "24"),           # 24 = Entertainment
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    init = requests.post(
        UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"}, json=meta, timeout=30,
        headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(size)})
    if init.status_code != 200 or not init.headers.get("Location", "").startswith("https://"):
        raise RuntimeError(f"upload session init failed: HTTP {init.status_code}")
    with mp4.open("rb") as fh:
        put = requests.put(init.headers["Location"], data=fh, timeout=600,
                           headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4",
                                    "Content-Length": str(size)})
    if put.status_code not in (200, 201):
        raise RuntimeError(f"upload failed: HTTP {put.status_code}")
    vid = (put.json() or {}).get("id")
    if not vid:
        raise RuntimeError("upload response had no video id")
    return str(vid)


__all__ = ["upload_short", "OAuthError"]
