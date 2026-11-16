"""Quota + abort tracking in state/quota.json: Kaggle weekly GPU hours, Gemini daily calls, abort backoff."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.common.config import models, settings
from src.common.state import load_state, save_state

DEFAULT: dict[str, Any] = {
    "kaggle": {"week_start": None, "gpu_hours_used": 0.0},
    "gemini": {"date": None, "calls": 0, "retry_after": {}},
    "aborts": {"consecutive": 0, "last_reason": "", "paused_until": None},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _week_start(now: datetime) -> str:
    return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")


class Quota:
    def __init__(self, now: datetime | None = None, name: str = "quota.json"):
        self.name = name
        self.now = now or _now()
        self.data = load_state(name, DEFAULT)
        for k, v in DEFAULT.items():
            self.data.setdefault(k, dict(v))
        self._roll()

    def _roll(self) -> None:
        wk = _week_start(self.now)
        if self.data["kaggle"].get("week_start") != wk:
            self.data["kaggle"] = {"week_start": wk, "gpu_hours_used": 0.0}
        day = self.now.strftime("%Y-%m-%d")
        if self.data["gemini"].get("date") != day:
            self.data["gemini"] = {"date": day, "calls": 0, "retry_after": self.data["gemini"].get("retry_after", {})}

    def save(self) -> None:
        save_state(self.name, self.data)

    # --- Kaggle weekly GPU budget -------------------------------------------------
    def kaggle_limit_hours(self) -> float:
        k = models()["kaggle"]
        return k["weekly_gpu_hours"] * k["stop_at_pct"] / 100.0

    def kaggle_can_spend(self, hours: float) -> bool:
        return self.data["kaggle"]["gpu_hours_used"] + hours <= self.kaggle_limit_hours()

    def kaggle_record(self, hours: float) -> None:
        self.data["kaggle"]["gpu_hours_used"] = round(self.data["kaggle"]["gpu_hours_used"] + hours, 3)

    # --- Gemini -------------------------------------------------------------------
    def gemini_record_call(self) -> None:
        self.data["gemini"]["calls"] += 1

    def gemini_rate_limited(self, model: str, retry_seconds: float) -> None:
        until = self.now + timedelta(seconds=max(1.0, retry_seconds))
        self.data["gemini"]["retry_after"][model] = until.isoformat()

    def gemini_model_available(self, model: str) -> bool:
        until = self.data["gemini"]["retry_after"].get(model)
        return not until or datetime.fromisoformat(until) <= self.now

    # --- Abort backoff ------------------------------------------------------------
    def is_paused(self) -> bool:
        until = self.data["aborts"].get("paused_until")
        return bool(until) and datetime.fromisoformat(until) > self.now

    def record_abort(self, reason: str) -> None:
        a = self.data["aborts"]
        a["consecutive"] += 1
        a["last_reason"] = reason
        cfg = settings()["abort"]
        if a["consecutive"] >= cfg["consecutive_limit"]:
            a["paused_until"] = (self.now + timedelta(hours=cfg["pause_hours"])).isoformat()

    def record_success(self) -> None:
        self.data["aborts"] = {"consecutive": 0, "last_reason": "", "paused_until": None}
