"""Tests for QuotaTracker, backoff pause, model discovery, and 404/429/5xx handling (§8)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.common import gemini, state as state_mod
from src.common.quota import QuotaTracker


def test_quota_spend_and_3_abort_backoff(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    qt = QuotaTracker(filename="quota_test.json")
    now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)

    assert qt.can_spend("text", 1)
    qt.spend("text", 2)
    assert qt.summary()["text_calls"] == 2

    qt.record_abort("err1", now=now)
    assert not qt.is_paused(now=now)[0]
    qt.record_abort("err2", now=now)
    assert not qt.is_paused(now=now)[0]
    qt.record_abort("err3", retry_delay_sec=24 * 3600, now=now)
    paused, until = qt.is_paused(now=now)
    assert paused
    assert datetime.fromisoformat(until) >= now + timedelta(hours=23)

    qt.record_success()
    assert not qt.is_paused(now=now)[0]


def test_model_discovery_and_error_classification(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(state_mod, "STATE_DIR", tmp_path)
    gemini.reset_skipped_models()

    assert gemini.classify_gemini_error(RuntimeError("404 NOT_FOUND")) == "not_found"
    assert gemini.classify_gemini_error(RuntimeError("429 RESOURCE_EXHAUSTED retryDelay: 45s")) == "rate_limit"
    assert gemini.extract_retry_delay_seconds(RuntimeError("retry in 1h2m3s")) == 3723.0
    assert gemini.classify_gemini_error(RuntimeError("503 Service Unavailable")) == "transient"

    class FakeModels:
        def __init__(self):
            self.calls = []

        def list(self):
            return [
                SimpleNamespace(name="models/gemini-3.8-flash", supported_actions=["generateContent"]),
                SimpleNamespace(name="models/gemini-3.6-flash", supported_actions=["generateContent"]),
            ]

        def generate_content(self, model: str, contents: str):
            self.calls.append(model)
            if model == "gemini-3.8-flash":
                raise RuntimeError("404 NOT_FOUND")
            return SimpleNamespace(text="hello from 3.6")

    fake_client = SimpleNamespace(models=FakeModels())
    discovered = gemini.discover_text_models(force_refresh=True, client=fake_client)
    assert discovered == ["gemini-3.8-flash", "gemini-3.6-flash"]

    qt = QuotaTracker(filename="quota_disc.json")
    txt, used = gemini.generate_text("hi", step="test", quota=qt, client=fake_client)
    assert txt == "hello from 3.6"
    assert used == "gemini-3.6-flash"

    # 404 model stays skipped on subsequent calls
    fake_client.models.calls.clear()
    txt2, _ = gemini.generate_text("hi2", step="test", quota=qt, client=fake_client)
    assert fake_client.models.calls == ["gemini-3.6-flash"]
    gemini.reset_skipped_models()
