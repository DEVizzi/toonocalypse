"""Tests for token expiry threshold, watchdog alerting, and secret-free behavior."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.tokens.instagram_auth import days_remaining, should_refresh_instagram


def test_instagram_refresh_threshold() -> None:
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    soon = (now + timedelta(days=10)).isoformat()
    plenty = (now + timedelta(days=40)).isoformat()
    assert days_remaining(soon, now=now) < 11
    assert should_refresh_instagram(soon, threshold_days=20.0, now=now)
    assert not should_refresh_instagram(plenty, threshold_days=20.0, now=now)
    assert should_refresh_instagram(None, threshold_days=20.0, now=now)
