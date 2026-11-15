"""Fetch Instagram Reels insights for published episodes."""
from __future__ import annotations

import os
from typing import Any

import requests


def fetch_instagram_media_stats(media_ids: list[str]) -> dict[str, dict[str, int]]:
    """Fetch reach, likes, comments, and shares from Instagram Graph API."""
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token or not media_ids:
        return {}
    stats: dict[str, dict[str, int]] = {}
    for mid in media_ids:
        resp = requests.get(
            f"https://graph.facebook.com/v21.0/{mid}",
            params={
                "fields": "like_count,comments_count,insights.metric(reach,plays,shares,saved)",
                "access_token": token,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            continue
        data: dict[str, Any] = resp.json()
        insights_map: dict[str, int] = {}
        for entry in data.get("insights", {}).get("data", []):
            vals = entry.get("values", [])
            if vals:
                insights_map[entry["name"]] = int(vals[0].get("value", 0))
        stats[mid] = {
            "likes": int(data.get("like_count", 0)),
            "comments": int(data.get("comments_count", 0)),
            "plays": insights_map.get("plays", 0),
            "reach": insights_map.get("reach", 0),
            "shares": insights_map.get("shares", 0),
            "saved": insights_map.get("saved", 0),
        }
    return stats
