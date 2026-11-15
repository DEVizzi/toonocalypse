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
    assert qt.summary()["text_calls"] == 2
    qt.enqueue_resume({"episode_id": "ep-99-pt2", "stage": "art"})
    popped = qt.pop_resume()
    assert popped == {"episode_id": "ep-99-pt2", "stage": "art"}
    assert qt.pop_resume() is None


def test_gemini_multi_key_failover(monkeypatch) -> None:
    import types
    import sys
    from src.common import gemini

    gemini.reset_exhausted_keys()
    monkeypatch.setenv("GOOGLE_API_KEY", "key-a")
    monkeypatch.setenv("GOOGLE_API_KEY1", "key-b")
    monkeypatch.setenv("GOOGLE_API_KEY2", "key-a")  # duplicate should be deduped
    monkeypatch.setenv("GOOGLE_API_KEYS", "key-c, key-b")

    keys = gemini.get_gemini_api_keys()
    assert keys == ["key-a", "key-b", "key-c"]

    class FakeClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(genai=types.SimpleNamespace(Client=FakeClient)))

    attempts: list[str] = []

    def fn(client):
        attempts.append(client.api_key)
        if client.api_key == "key-a":
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
        return f"ok:{client.api_key}"

    assert gemini.call_with_key_failover(fn) == "ok:key-b"
    assert attempts == ["key-a", "key-b"]
    # Subsequent call skips exhausted key-a
    attempts.clear()
    assert gemini.call_with_key_failover(fn) == "ok:key-b"
    assert attempts == ["key-b"]
    gemini.reset_exhausted_keys()
