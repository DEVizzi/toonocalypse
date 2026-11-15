"""YouTube Data API v3 publisher with idempotency, clean titles, and playlists (§10.H & §11)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from googleapiclient.http import MediaFileUpload

from src.common.config import load_settings
from src.moderation.gate import check_metadata
from src.tokens.youtube_auth import build_youtube_client


def format_youtube_title(raw_title: str, part_num: int, part_count: int) -> str:
    clean = " ".join(raw_title.strip().split())
    suffix = f" Pt {part_num}/{part_count}" if part_count > 1 else ""
    max_base = 60 - len(suffix)
    if len(clean) > max_base:
        clean = clean[: max_base - 1].rstrip() + "…"
    return f"{clean}{suffix}"


def find_existing_youtube_video(youtube: Any, episode_id: str) -> str | None:
    resp = youtube.search().list(part="id,snippet", forMine=True, type="video", q=episode_id, maxResults=5).execute()
    marker = f"[ep:{episode_id}]"
    for item in resp.get("items", []):
        if marker in item.get("snippet", {}).get("description", ""):
            return item["id"]["videoId"]
    return None


def publish_to_youtube(
    video_path: Path,
    episode_id: str,
    title: str,
    description: str,
    tags: list[str],
    part_num: int = 1,
    part_count: int = 1,
) -> str:
    cfg = load_settings()
    yt_title = format_youtube_title(title, part_num, part_count)
    full_desc = f"{description.strip()}\n\n[ep:{episode_id}]"
    mod = check_metadata(yt_title, full_desc, "", tags)
    if not mod.passed:
        raise ValueError(f"YouTube metadata blocked by moderation: {mod.reasons}")

    youtube = build_youtube_client()
    existing = find_existing_youtube_video(youtube, episode_id)
    if existing:
        return existing

    body = {
        "snippet": {
            "title": yt_title,
            "description": full_desc,
            "tags": tags[:10],
            "categoryId": str(cfg.get("youtube_category_id", "1")),
        },
        "status": {
            "privacyStatus": str(cfg.get("youtube_privacy", "private")),
            "selfDeclaredMadeForKids": bool(cfg.get("self_declared_made_for_kids", False)),
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]
