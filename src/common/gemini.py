"""Single-key Gemini v1beta client with 24h model discovery and 404/429/5xx error handling (§2)."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from src.common.config import load_models
from src.common.quota import QuotaTracker
from src.common.state import load_state, save_state


class AllTextModelsFailed(RuntimeError):
    """Raised when every discovered Gemini text model fails; triggers clean abort."""


_SKIPPED_MODELS: set[str] = set()


def reset_skipped_models() -> None:
    _SKIPPED_MODELS.clear()


def has_gemini_key() -> bool:
    return bool(os.environ.get("GOOGLE_API_KEY", "").strip())


def get_client() -> Any:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not set")
    api_ver = os.environ.get("GOOGLE_GENAI_API_VERSION", "v1beta").strip() or "v1beta"
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(api_version=api_ver))


def _normalize_model_name(name: str) -> str:
    return name.removeprefix("models/").strip()


def _supports_generate_content(model_obj: Any) -> bool:
    actions = getattr(model_obj, "supported_actions", None) or getattr(model_obj, "supported_generation_methods", None)
    if not actions:
        return True
    return any("generateContent" in str(a) for a in actions)


def discover_text_models(force_refresh: bool = False, client: Any | None = None) -> list[str]:
    """Call client.models.list() once/24h, keep configured text_models that exist & support generateContent."""
    configured = load_models().get("text_models", ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemma-4"])
    now = datetime.now(timezone.utc)
    if not force_refresh:
        cache = load_state("models_cache.json", {})
        cached_at = cache.get("cached_at")
        cached_models = cache.get("text_models")
        if cached_at and isinstance(cached_models, list):
            dt = datetime.fromisoformat(str(cached_at).replace("Z", "+00:00"))
            if now - dt < timedelta(hours=24):
                return [m for m in cached_models if m not in _SKIPPED_MODELS]

    cli = client or get_client()
    available: dict[str, Any] = {}
    for m in cli.models.list():
        short = _normalize_model_name(getattr(m, "name", ""))
        if short and _supports_generate_content(m):
            available[short] = m

    matched = [cfg for cfg in configured if _normalize_model_name(cfg) in available]
    save_state(
        "models_cache.json",
        {
            "cached_at": now.isoformat(),
            "api_version": os.environ.get("GOOGLE_GENAI_API_VERSION", "v1beta"),
            "text_models": matched,
            "available_count": len(available),
        },
    )
    return [m for m in matched if m not in _SKIPPED_MODELS]


def extract_retry_delay_seconds(exc: Exception) -> float:
    msg = str(exc)
    m = re.search(r"retry(?:Delay| in)['\":\s]+(?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s", msg, re.IGNORECASE)
    if not m:
        return 60.0
    hours = float(m.group(1) or 0)
    mins = float(m.group(2) or 0)
    secs = float(m.group(3) or 0)
    return max(1.0, hours * 3600.0 + mins * 60.0 + secs)


def classify_gemini_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "404" in msg or "not_found" in msg or "not found" in msg or "no longer available" in msg:
        return "not_found"
    if "429" in msg or "resource_exhausted" in msg or "quota" in msg or "rate" in msg:
        return "rate_limit"
    if any(code in msg for code in ("500", "502", "503", "504", "timeout", "timed out", "temporarily unavailable", "connection")):
        return "transient"
    return "fatal"


def generate_text(
    contents: Any,
    *,
    step: str = "text",
    quota: QuotaTracker | None = None,
    client: Any | None = None,
) -> tuple[str, str]:
    """Generate text using discovered v1beta models with 404/429/5xx handling. Never returns template text."""
    qt = quota or QuotaTracker()
    if not qt.can_spend("text", 1):
        raise AllTextModelsFailed("Daily text quota limit reached")

    cli = client or get_client()
    models = discover_text_models(client=cli)
    if not models:
        raise AllTextModelsFailed("No usable text models found in v1beta models.list()")

    last_exc: Exception | None = None
    for model in models:
        if model in _SKIPPED_MODELS:
            continue
        for attempt in range(3):
            try:
                resp = cli.models.generate_content(model=model, contents=contents)
                qt.spend("text", 1)
                print(f"[gemini:{step}] served by {model}")
                return (resp.text or ""), model
            except Exception as exc:
                last_exc = exc
                kind = classify_gemini_error(exc)
                if kind == "not_found":
                    _SKIPPED_MODELS.add(model)
                    print(f"[gemini:{step}] {model} returned 404/not_found; skipping for rest of run")
                    break
                if kind == "rate_limit":
                    delay = extract_retry_delay_seconds(exc)
                    qt.record_retry_delay(model, delay)
                    print(f"[gemini:{step}] {model} rate-limited (429, retryDelay={delay:.0f}s); trying next model")
                    break
                if kind == "transient" and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                print(f"[gemini:{step}] {model} failed ({type(exc).__name__}); trying next model")
                break

    raise AllTextModelsFailed(f"All Gemini text models failed: {last_exc}")
