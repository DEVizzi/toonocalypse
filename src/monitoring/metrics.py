"""Pipeline metrics collection and summarization."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.common.quota import QuotaTracker
from src.common.state import load_state


def collect_pipeline_metrics() -> dict[str, Any]:
    """Aggregate current pipeline health, quota, buffer, and QA metrics."""
    published = load_state("published.json", default={"episodes": {}})
    qa_log = load_state("qa_log.json", default={"entries": []})
    tokens = load_state("tokens.json", default={})
    bible = load_state("story_bible.json", default={})
    quota = QuotaTracker().summary()

    episodes = published.get("episodes", {})
    yt_count = sum(1 for e in episodes.values() if e.get("youtube", {}).get("id"))
    ig_count = sum(1 for e in episodes.values() if e.get("instagram", {}).get("id"))

    qa_entries = qa_log.get("entries", [])
    recent_qa = qa_entries[-50:]
    qa_pass = sum(1 for e in recent_qa if e.get("passed", True))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "published_total": len(episodes),
        "youtube_published": yt_count,
        "instagram_published": ig_count,
        "active_arc": bible.get("active_arc"),
        "used_ideas_count": len(bible.get("used_ideas", [])),
        "qa_recent_total": len(recent_qa),
        "qa_recent_pass": qa_pass,
        "quota": quota,
        "tokens": {
            "youtube_last_refresh": tokens.get("youtube_last_refresh"),
            "instagram_last_refresh": tokens.get("instagram_last_refresh"),
            "instagram_expires_at": tokens.get("instagram_expires_at"),
        },
    }
