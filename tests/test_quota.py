from datetime import datetime, timedelta, timezone

import pytest

import src.common.state as state_mod
from src.common.quota import Quota

NOW = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)  # a Tuesday


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)


def test_kaggle_stops_at_85_percent():
    q = Quota(now=NOW)
    limit = q.kaggle_limit_hours()  # 30 * 0.85 = 25.5
    assert limit == pytest.approx(25.5)
    q.kaggle_record(25.0)
    assert q.kaggle_can_spend(0.5)
    assert not q.kaggle_can_spend(0.6)


def test_kaggle_weekly_reset():
    q = Quota(now=NOW)
    q.kaggle_record(20)
    q.save()
    next_week = Quota(now=NOW + timedelta(days=7))
    assert next_week.data["kaggle"]["gpu_hours_used"] == 0


def test_gemini_daily_reset_keeps_retry_after():
    q = Quota(now=NOW)
    q.gemini_record_call()
    q.gemini_rate_limited("gemini-x", 3600)
    q.save()
    later = Quota(now=NOW + timedelta(minutes=30))
    assert not later.gemini_model_available("gemini-x")
    tomorrow = Quota(now=NOW + timedelta(days=1))
    assert tomorrow.data["gemini"]["calls"] == 0
    assert tomorrow.gemini_model_available("gemini-x")


def test_three_aborts_pause_then_success_clears():
    q = Quota(now=NOW)
    for i in range(2):
        q.record_abort(f"r{i}")
    assert not q.is_paused()
    q.record_abort("r2")
    assert q.is_paused()
    q.record_success()
    assert not q.is_paused() and q.data["aborts"]["consecutive"] == 0
