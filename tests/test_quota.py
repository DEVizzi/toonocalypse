"""Tests for daily Gemini quota tracking and resume queue."""
from __future__ import annotations

from pathlib import Path

from src.common import state as state_mod
from src.common.quota import QuotaTracker


def test_quota_spend_and_resume_queue(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    qt = QuotaTracker(filename="quota_test.json")
    assert qt.can_spend("text", 1)
    qt.spend("text", 2)
    assert qt.summary()["text"] == 2
    qt.enqueue_resume({"story_id": "ep-99", "part_num": 2})
    popped = qt.pop_resume()
    assert popped == {"story_id": "ep-99", "part_num": 2}
    assert qt.pop_resume() is None
