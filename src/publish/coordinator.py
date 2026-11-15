"""Daily one-per-day publish coordinator with per-platform idempotency (§4 & §11)."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.common.config import load_settings
from src.common.state import load_state, save_state


def today_local_str(now: datetime | None = None) -> str:
    tz_name = load_settings().get("audience_timezone", "Asia/Kolkata")
    tz = ZoneInfo(tz_name)
    ref = now.astimezone(tz) if now else datetime.now(tz)
    return ref.strftime("%Y-%m-%d")


def can_publish_episode_today(episode_id: str, pub_state: dict[str, Any] | None = None, day_str: str | None = None) -> bool:
    """Enforce HARD RULE: at most ONE new episode per day (retries for the same day's episode are allowed)."""
    state = pub_state if pub_state is not None else load_state("published.json", {"episodes": {}, "daily_posts": {}})
    day = day_str or today_local_str()
    posted_ep = state.get("daily_posts", {}).get(day)
    if posted_ep is None:
        return True
    return posted_ep == episode_id


def record_platform_publish(episode_id: str, platform: str, media_id: str, day_str: str | None = None) -> dict[str, Any]:
    state = load_state("published.json", {"episodes": {}, "daily_posts": {}, "playlists": {}, "compilations": []})
    day = day_str or today_local_str()
    state.setdefault("daily_posts", {})[day] = episode_id
    ep = state.setdefault("episodes", {}).setdefault(episode_id, {})
    ep[platform] = {"id": media_id, "published_at": datetime.now(ZoneInfo("UTC")).isoformat()}
    save_state("published.json", state)
    return state
