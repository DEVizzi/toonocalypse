"""Self-learning loop updating state/performance.json and bounded playbook weights."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yaml

from src.analytics.instagram_insights import fetch_instagram_media_stats
from src.analytics.youtube_analytics import fetch_youtube_video_stats
from src.common.config import CONFIG_DIR, load_playbook
from src.common.state import load_state, save_state


def _clamp(val: float, lo: float = 0.5, hi: float = 2.0) -> float:
    return round(max(lo, min(hi, val)), 3)


def run_learning_loop(offline: bool = False) -> dict[str, Any]:
    """Pull platform analytics, score episodes, and adjust bounded playbook weights."""
    published = load_state("published.json", default={"episodes": {}})
    perf = load_state("performance.json", default={"episodes": {}, "last_run": None})
    episodes: dict[str, Any] = published.get("episodes", {})

    yt_ids = [e["youtube"]["id"] for e in episodes.values() if isinstance(e.get("youtube"), dict) and e["youtube"].get("id")]
    ig_ids = [e["instagram"]["id"] for e in episodes.values() if isinstance(e.get("instagram"), dict) and e["instagram"].get("id")]

    yt_stats = {} if offline else fetch_youtube_video_stats(yt_ids)
    ig_stats = {} if offline else fetch_instagram_media_stats(ig_ids)

    scores: list[tuple[str, float]] = []
    for ep_id, ep in episodes.items():
        yt_id = ep.get("youtube", {}).get("id", "") if isinstance(ep.get("youtube"), dict) else ""
        ig_id = ep.get("instagram", {}).get("id", "") if isinstance(ep.get("instagram"), dict) else ""
        y = yt_stats.get(yt_id, {})
        g = ig_stats.get(ig_id, {})
        score = (
            y.get("views", 0)
            + 5 * y.get("likes", 0)
            + 10 * y.get("comments", 0)
            + g.get("plays", 0)
            + 5 * g.get("likes", 0)
            + 15 * g.get("shares", 0)
        )
        perf.setdefault("episodes", {})[ep_id] = {
            "youtube": y,
            "instagram": g,
            "score": score,
            "format": ep.get("format", "One-Shot"),
            "heroes": ep.get("heroes", []),
            "cliffhanger_type": ep.get("cliffhanger_type", ""),
        }
        scores.append((ep_id, float(score)))

    perf["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state("performance.json", perf)

    playbook = load_playbook()
    if scores:
        avg = sum(s for _, s in scores) / len(scores)
        fmt_weights = playbook.setdefault("format_weights", {})
        for ep_id, score in scores:
            ep = perf["episodes"][ep_id]
            fmt = ep.get("format", "One-Shot")
            if fmt in fmt_weights and avg > 0:
                delta = 0.05 if score >= avg else -0.03
                fmt_weights[fmt] = _clamp(float(fmt_weights[fmt]) + delta)

        playbook_path = CONFIG_DIR / "playbook.yaml"
        playbook_path.write_text(yaml.safe_dump(playbook, sort_keys=False), encoding="utf-8")

    return {"episodes_scored": len(scores), "last_run": perf["last_run"]}
