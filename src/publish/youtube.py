"""YouTube Shorts uploader, metadata updater, commenter & transactional rollback deleter (v4.6).

Security:
- OAuth access token only in `Authorization: Bearer` header; never in URLs or logs.
- Strict ID validation before any write call; API error reasons are redacted before they are raised/logged.
- `delete_video(video_id)` removes a partially published YouTube Short if Instagram `media_publish` or the 10-minute
  watchdog triggers rollback, preventing duplicate videos on Attempt 2.
- Comments and metadata updates need the `youtube.force-ssl` (or `youtube`) OAuth scope; callers treat them as
  best-effort extras that never block or roll back a published episode.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Sequence

from src.publish.alerts import redact
from src.publish.oauth import OAuthError, access_token, assert_expected_channel

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
MAX_BYTES = 256 * 1024 * 1024
PRIVACY = ("public", "unlisted", "private")
DEFAULT_CATEGORY_ID = "20"     # Gaming
_SAFE_VID = re.compile(r"^[A-Za-z0-9_\-]{6,24}$")
_SAFE_CHANNEL = re.compile(r"^UC[A-Za-z0-9_\-]{20,30}$")


def _requests():
    import requests
    return requests


def _clip(s: str, n: int) -> str:
    s = " ".join(str(s).replace("<", "").replace(">", "").split())
    return s[:n]


def _clean_desc(s: str, n: int) -> str:
    """Like `_clip` but keeps line breaks (YouTube rejects `<`/`>`; collapses 3+ blank lines)."""
    lines = [" ".join(ln.replace("<", "").replace(">", "").split()) for ln in str(s or "").splitlines()]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return out[:n]


def _clean_tags(tags: Sequence[str]) -> list[str]:
    return [t for t in (_clip(str(t).replace(",", " "), 30) for t in (tags or [])) if t][:15]


def _category(category_id: str | None) -> str:
    cat = str(category_id or os.environ.get("YT_CATEGORY_ID") or DEFAULT_CATEGORY_ID).strip()
    return cat if cat.isdigit() else DEFAULT_CATEGORY_ID


def _valid_vid(video_id: str) -> str:
    vid = str(video_id or "").strip()
    if not _SAFE_VID.match(vid):
        raise ValueError("invalid YouTube video_id")
    return vid


def _api_reason(resp: Any) -> str:
    try:
        err = (resp.json() or {}).get("error") or {}
        reasons = [str(e.get("reason", "")) for e in (err.get("errors") or []) if isinstance(e, dict)]
        msg = ",".join(r for r in reasons if r) or str(err.get("status") or err.get("message") or "")
    except (ValueError, AttributeError):
        msg = "non-JSON error"
    return redact(msg)[:120]


def upload_short(mp4: Path, title: str, description: str, tags: list[str], privacy: str = "public",
                 category_id: str | None = None) -> str:
    """Uploads `mp4` (`selfDeclaredMadeForKids: false`) and returns the new YouTube `video_id`."""
    if privacy not in PRIVACY:
        raise ValueError("invalid privacy status")
    size = mp4.stat().st_size
    if not (0 < size <= MAX_BYTES):
        raise RuntimeError("video size out of bounds")
    req = _requests()
    token, _, _ = access_token()
    if (os.environ.get("YOUTUBE_EXPECTED_CHANNEL_ID") or "").strip():
        assert_expected_channel(token)   # fail closed: never upload to the wrong brand channel
    meta = {
        "snippet": {
            "title": _clip(title, 100),
            "description": _clean_desc(description, 4800),
            "tags": _clean_tags(tags),
            "categoryId": _category(category_id),
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


def update_video_metadata(video_id: str, title: str, description: str, tags: Sequence[str],
                          category_id: str | None = None) -> bool:
    """Replaces title/description/tags/category of an existing video (`videos.update`, part=snippet)."""
    vid = _valid_vid(video_id)
    req = _requests()
    token, _, _ = access_token()
    body = {
        "id": vid,
        "snippet": {
            "title": _clip(title, 100),
            "description": _clean_desc(description, 4800),
            "tags": _clean_tags(tags),
            "categoryId": _category(category_id),
        },
    }
    resp = req.put(VIDEOS_URL, params={"part": "snippet"}, json=body,
                   headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"videos.update failed: HTTP {resp.status_code} ({_api_reason(resp)})")
    return True


def _own_channel_id(req: Any, token: str) -> str | None:
    try:
        resp = req.get(CHANNELS_URL, params={"part": "id", "mine": "true"},
                       headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if resp.status_code != 200:
            return None
        items = (resp.json() or {}).get("items") or []
    except (req.RequestException, ValueError):
        return None
    cid = str(items[0].get("id") or "") if items and isinstance(items[0], dict) else ""
    return cid if _SAFE_CHANNEL.match(cid) else None


def post_comment(video_id: str, text: str, channel_id: str | None = None) -> str:
    """Posts a top-level comment from the channel on `video_id` (`commentThreads.insert`). Returns the thread id.
    Pinning is not available in the YouTube Data API, so pin it manually in the app/Studio."""
    vid = _valid_vid(video_id)
    body_text = _clean_desc(text, 9000)
    if not body_text:
        raise ValueError("empty comment text")
    req = _requests()
    token, _, _ = access_token()
    cid = channel_id if (channel_id and _SAFE_CHANNEL.match(channel_id)) else _own_channel_id(req, token)
    snippet: dict[str, Any] = {"videoId": vid, "topLevelComment": {"snippet": {"textOriginal": body_text}}}
    if cid:
        snippet["channelId"] = cid
    resp = req.post(COMMENT_THREADS_URL, params={"part": "snippet"}, json={"snippet": snippet},
                    headers={"Authorization": f"Bearer {token}"}, timeout=25)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"commentThreads.insert failed: HTTP {resp.status_code} ({_api_reason(resp)})")
    new_id = str((resp.json() or {}).get("id") or "").strip()
    if not new_id:
        raise RuntimeError("commentThreads.insert returned no id")
    return new_id


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


__all__ = ["OAuthError", "delete_video", "post_comment", "update_video_metadata", "upload_short"]
