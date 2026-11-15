"""Daily API quota tracker with resume-later queue (single GOOGLE_API_KEY)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.common.config import load_models
from src.common.retry import QuotaExceededError
from src.common.state import load_state, save_state


class QuotaTracker:
    def __init__(self, filename: str = "quota.json"):
        self.filename = filename
        self.limits = load_models().get("quota", {})

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load(self) -> dict[str, Any]:
        data = load_state(self.filename, {"date": "", "text_calls": 0, "image_calls": 0, "vision_calls": 0, "pending_jobs": []})
        today = self._today()
        if data.get("date") != today:
            data["date"] = today
            data["text_calls"] = 0
            data["image_calls"] = 0
            data["vision_calls"] = 0
        return data

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
