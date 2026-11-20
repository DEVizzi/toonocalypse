"""YouTube Shorts uploader & transactional rollback deleter (v4.5).

Security:
- OAuth access token only in `Authorization: Bearer` header; never in URLs or logs.
- `delete_video(video_id)` validates video ID format and removes a partially published YouTube Short if Instagram
  `media_publish` or the 10-minute watchdog triggers rollback, preventing duplicate videos on Attempt 2.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from src.publish.oauth import OAuthError, access_token

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
MAX_BYTES = 256 * 1024 * 1024
PRIVACY = ("public", "unlisted", "private")
_SAFE_VID = re.compile(r"^[A-Za-z0-9_\-]{6,24}$")


def _requests():
    import requests
    return requests


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).replace("<", "").replace(">", "").split())
    return s[:n]


def upload_short(mp4: Path, title: str, description: str, tags: list[str], privacy: str = "public") -> str:
    """Uploads `mp4` (`selfDeclaredMadeForKids: false`) and returns the new YouTube `video_id`."""
    if privacy not in PRIVACY:
        raise ValueError("invalid privacy status")
    size = mp4.stat().st_size
    if not (0 < size <= MAX_BYTES):
        raise RuntimeError("video size out of bounds")
    req = _requests()
    token, _, _ = access_token()
    meta = {
        "snippet": {
            "title": _clip(title, 100),
            "description": _clip(description, 4800),
            "tags": [_clip(t, 30) for t in tags][:15],
            "categoryId": os.environ.get("YT_CATEGORY_ID", "24"),
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    init = req.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        json=meta,
        timeout=30,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
    )
    if init.status_code != 200 or not init.headers.get("Location", "").startswith("https://"):
        raise RuntimeError(f"upload session init failed: HTTP {init.status_code}")
    with mp4.open("rb") as fh:
        put = req.put(
            init.headers["Location"],
            data=fh,
            timeout=300,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "video/mp4",
                "Content-Length": str(size),
            },
        )
    if put.status_code not in (200, 201):
        raise RuntimeError(f"upload failed: HTTP {put.status_code}")
    vid = (put.json() or {}).get("id")
    if not vid or not _SAFE_VID.match(str(vid)):
        raise RuntimeError("upload response had no valid video id")
    return str(vid)


def delete_video(video_id: str) -> bool:
    """Deletes a YouTube video by ID during transactional rollback (`videos.delete`). Returns True on HTTP 204/404."""
    vid = str(video_id or "").strip()
    if not vid:
        return False
    if not _SAFE_VID.match(vid):
        raise ValueError("invalid YouTube video_id")
    req = _requests()
    token, _, _ = access_token()
    resp = req.delete(
        VIDEOS_URL,
        params={"id": vid},
        headers={"Authorization": f"Bearer {token}"},
        timeout=25,
    )
    return resp.status_code in (200, 204, 404)


__all__ = ["OAuthError", "delete_video", "upload_short"]
