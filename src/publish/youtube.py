"""YouTube Data API v3: fresh access token from the refresh token, resumable Shorts upload, playlist per story,
idempotency via a hidden episode tag, and a 'Next part' link added to the previous part's description."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from src.common.config import settings

API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"


def access_token() -> str:
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YOUTUBE_CLIENT_ID"], "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"YouTube token refresh failed: {r.status_code} {r.json().get('error')}")
    return r.json()["access_token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def find_existing(tok: str, episode_id: str) -> str | None:
    """Search our own uploads for the hidden episode tag (idempotency)."""
    ch = requests.get(f"{API}/channels", params={"part": "contentDetails", "mine": "true"}, headers=_h(tok), timeout=30).json()
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = requests.get(f"{API}/playlistItems", params={"part": "contentDetails", "playlistId": uploads, "maxResults": 25},
                         headers=_h(tok), timeout=30).json().get("items", [])
    ids = ",".join(i["contentDetails"]["videoId"] for i in items)
    if not ids:
        return None
    vids = requests.get(f"{API}/videos", params={"part": "snippet", "id": ids}, headers=_h(tok), timeout=30).json().get("items", [])
    for v in vids:
        if episode_id in (v["snippet"].get("tags") or []):
            return v["id"]
    return None


def upload(tok: str, video: Path, title: str, description: str, episode_id: str) -> str:
    pub = settings()["publish"]
    body = {"snippet": {"title": title[:100], "description": description, "categoryId": pub["youtube_category_id"],
                        "tags": [episode_id, settings()["series_name"], "motion comic", "Shorts"]},
            "status": {"privacyStatus": pub["youtube_privacy"], "selfDeclaredMadeForKids": bool(pub["made_for_kids"])}}
    init = requests.post(UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"},
                         headers=_h(tok) | {"Content-Type": "application/json", "X-Upload-Content-Type": "video/mp4",
                                            "X-Upload-Content-Length": str(video.stat().st_size)},
                         data=json.dumps(body), timeout=60)
    init.raise_for_status()
    with open(video, "rb") as f:
        r = requests.put(init.headers["Location"], data=f, headers=_h(tok) | {"Content-Type": "video/mp4"}, timeout=900)
    r.raise_for_status()
    return r.json()["id"]


def set_thumbnail(tok: str, video_id: str, cover: Path) -> None:
    with open(cover, "rb") as f:
        requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set", params={"videoId": video_id},
                      headers=_h(tok) | {"Content-Type": "image/jpeg"}, data=f, timeout=120)  # best effort


def ensure_playlist(tok: str, title: str, description: str, existing: str | None) -> str:
    if existing:
        return existing
    r = requests.post(f"{API}/playlists", params={"part": "snippet,status"}, headers=_h(tok), json={
        "snippet": {"title": title[:150], "description": description[:5000]},
        "status": {"privacyStatus": settings()["publish"]["youtube_privacy"]}}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def add_to_playlist(tok: str, playlist_id: str, video_id: str, position: int) -> None:
    requests.post(f"{API}/playlistItems", params={"part": "snippet"}, headers=_h(tok), json={
        "snippet": {"playlistId": playlist_id, "position": position,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id}}}, timeout=30).raise_for_status()


def append_next_link(tok: str, prev_video_id: str, next_video_id: str) -> None:
    v = requests.get(f"{API}/videos", params={"part": "snippet", "id": prev_video_id}, headers=_h(tok), timeout=30).json()["items"][0]
    sn = v["snippet"]
    link = f"Next part: https://youtube.com/shorts/{next_video_id}"
    if link in sn["description"]:
        return
    sn["description"] = f"{sn['description']}\n{link}"
    requests.put(f"{API}/videos", params={"part": "snippet"}, headers=_h(tok),
                 json={"id": prev_video_id, "snippet": {k: sn[k] for k in ("title", "description", "categoryId", "tags") if k in sn}},
                 timeout=30).raise_for_status()
