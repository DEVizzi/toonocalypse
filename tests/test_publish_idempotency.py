"""Tests for 1-episode-per-day publishing rule, idempotency, and YouTube title formatting."""
from __future__ import annotations

from src.publish.coordinator import can_publish_episode_today
from src.publish.youtube import format_youtube_title


def test_one_episode_per_day_and_same_episode_retry() -> None:
    state = {"daily_posts": {"2026-11-16": "ep-001"}, "episodes": {}}
    assert can_publish_episode_today("ep-001", pub_state=state, day_str="2026-11-16")
    assert not can_publish_episode_today("ep-002", pub_state=state, day_str="2026-11-16")
    assert can_publish_episode_today("ep-002", pub_state=state, day_str="2026-11-17")


def test_format_youtube_title_length_and_shorts_tag() -> None:
    t1 = format_youtube_title("The Runaway Espresso Machine", 1, 3)
    assert "#Shorts" in t1
    assert "Pt 1/3" in t1
    assert len(t1) <= 100

    t2 = format_youtube_title("A" * 120, 2, 4)
    assert len(t2) <= 100
    assert "#Shorts" in t2
