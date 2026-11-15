"""Fetch YouTube video statistics for published episodes."""
from __future__ import annotations

from typing import Any

from src.tokens.youtube_auth import build_youtube_client


def fetch_youtube_video_stats(video_ids: list[str]) -> dict[str, dict[str, int]]:
    """Fetch view, like, and comment counts from YouTube Data API v3."""
    if not video_ids:
        return {}
    yt = build_youtube_client()
    stats: dict[str, dict[str, int]] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        resp = yt.videos().list(part="statistics", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            s: dict[str, Any] = item.get("statistics", {})
            stats[item["id"]] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
            }
    return stats
