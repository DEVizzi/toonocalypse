"""Daily API quota, backoff pause state, and resume-later queue (single GOOGLE_API_KEY)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from src.common.config import load_models
from src.common.retry import QuotaExceededError
from src.common.state import load_state, save_state


class QuotaTracker:
    def __init__(self, filename: str = "quota.json"):
        self.filename = filename
        self.limits = load_models().get("quota", {})

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _today(self) -> str:
        return self._now().strftime("%Y-%m-%d")

    def _load(self) -> dict[str, Any]:
        default = {
            "date": "",
            "text_calls": 0,
            "vision_calls": 0,
            "tts_calls": 0,
            "paused_until": None,
            "consecutive_aborts": 0,
            "last_abort_reason": None,
            "last_abort_at": None,
            "model_retry_after": {},
            "pending_jobs": [],
        }
        data = load_state(self.filename, default)
        for k, v in default.items():
            data.setdefault(k, v)
        today = self._today()
        if data.get("date") != today:
            data["date"] = today
            data["text_calls"] = 0
            data["vision_calls"] = 0
            data["tts_calls"] = 0
            data["model_retry_after"] = {}
        return data

    def is_paused(self, now: datetime | None = None) -> tuple[bool, str | None]:
        data = self._load()
        pu = data.get("paused_until")
        if not pu:
            return False, None
        ref = now or self._now()
        dt = datetime.fromisoformat(str(pu).replace("Z", "+00:00"))
        if dt > ref:
            return True, str(pu)
        return False, None

    def record_retry_delay(self, model: str, retry_delay_sec: float, now: datetime | None = None) -> None:
        data = self._load()
        ref = now or self._now()
        until = (ref + timedelta(seconds=max(1.0, retry_delay_sec))).isoformat()
        data.setdefault("model_retry_after", {})[model] = {
            "retry_delay_sec": float(retry_delay_sec),
            "until": until,
        }
        save_state(self.filename, data)

    def record_abort(self, reason: str, retry_delay_sec: float = 0.0, now: datetime | None = None) -> dict[str, Any]:
        data = self._load()
        ref = now or self._now()
        count = int(data.get("consecutive_aborts", 0)) + 1
        data["consecutive_aborts"] = count
        data["last_abort_reason"] = reason
        data["last_abort_at"] = ref.isoformat()

        max_aborts = int(self.limits.get("max_consecutive_aborts", 3))
        if count >= max_aborts:
            pause_hours = float(self.limits.get("pause_hours", 12))
            longest_model_delay = max(
                [float(retry_delay_sec)]
                + [float(v.get("retry_delay_sec", 0.0)) for v in data.get("model_retry_after", {}).values() if isinstance(v, dict)]
            )
            delay_sec = max(pause_hours * 3600.0, longest_model_delay)
            data["paused_until"] = (ref + timedelta(seconds=delay_sec)).isoformat()
        save_state(self.filename, data)
        return data

    def record_success(self) -> None:
        data = self._load()
        data["consecutive_aborts"] = 0
        data["paused_until"] = None
        data["last_abort_reason"] = None
        save_state(self.filename, data)

    def can_spend(self, kind: str, count: int = 1) -> bool:
        data = self._load()
        key = f"{kind}_calls"
        limit = int(self.limits.get(f"daily_{kind}_limit", 1000))
        return int(data.get(key, 0)) + count <= limit

    def spend(self, kind: str, count: int = 1) -> None:
        data = self._load()
        key = f"{kind}_calls"
        limit = int(self.limits.get(f"daily_{kind}_limit", 1000))
        if int(data.get(key, 0)) + count > limit:
            raise QuotaExceededError(f"Daily {kind} quota limit ({limit}) reached")
        data[key] = int(data.get(key, 0)) + count
        save_state(self.filename, data)

    def enqueue_resume(self, job: dict[str, Any]) -> None:
        data = self._load()
        pending = data.setdefault("pending_jobs", [])
        if not any(j.get("episode_id") == job.get("episode_id") and j.get("stage") == job.get("stage") for j in pending):
            pending.append(job)
        save_state(self.filename, data)

    def pop_resume(self) -> dict[str, Any] | None:
        data = self._load()
        pending = data.get("pending_jobs", [])
        if not pending:
            return None
        job = pending.pop(0)
        save_state(self.filename, data)
        return job

    def summary(self) -> dict[str, Any]:
        return self._load()
