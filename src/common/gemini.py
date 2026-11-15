"""Multi-key Gemini API client helper with automatic quota/failure failover."""
from __future__ import annotations

import os
from typing import Callable, TypeVar

T = TypeVar("T")

_EXHAUSTED_KEYS: set[str] = set()


def get_gemini_api_keys() -> list[str]:
    """Return unique non-empty Gemini API keys from env in priority order."""
    candidates: list[str] = []
    for name in (
        "GOOGLE_API_KEY",
        "GOOGLE_API_KEY1",
        "GOOGLE_API_KEY2",
        "GOOGLE_API_KEY3",
        "GOOGLE_API_KEY_1",
        "GOOGLE_API_KEY_2",
        "GOOGLE_API_KEY_3",
    ):
        val = os.environ.get(name, "").strip()
        if val:
            candidates.append(val)
    extra = os.environ.get("GOOGLE_API_KEYS", "").strip()
    if extra:
        for item in extra.split(","):
            val = item.strip()
            if val:
                candidates.append(val)

    seen: set[str] = set()
    unique: list[str] = []
    for key in candidates:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def has_gemini_keys() -> bool:
    """Return True if at least one non-exhausted Gemini API key is available."""
    return any(k not in _EXHAUSTED_KEYS for k in get_gemini_api_keys())


def reset_exhausted_keys() -> None:
    """Clear exhausted-key cache (useful in unit tests)."""
    _EXHAUSTED_KEYS.clear()


def call_with_key_failover(fn: Callable[[object], T]) -> T:
    """Execute fn(genai.Client) across configured keys, failing over on quota/API errors."""
    from google import genai

    keys = get_gemini_api_keys()
    active = [k for k in keys if k not in _EXHAUSTED_KEYS]
    if not active and keys:
        # If all keys were marked exhausted earlier in a long run, allow one fresh pass
        _EXHAUSTED_KEYS.clear()
        active = list(keys)
    if not active:
        raise RuntimeError("No Gemini API keys configured (GOOGLE_API_KEY / GOOGLE_API_KEY1..)")

    last_exc: Exception | None = None
    for idx, key in enumerate(active, start=1):
        try:
            client = genai.Client(api_key=key)
            return fn(client)
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            if any(tok in msg for tok in ("429", "quota", "resource_exhausted", "rate", "limit", "403", "401", "expired", "invalid")):
                _EXHAUSTED_KEYS.add(key)
            print(f"[gemini] key #{idx}/{len(active)} ({key[:6]}...) failed ({type(exc).__name__}: {str(exc)[:140]}); failing over...")
            continue

    assert last_exc is not None
    raise last_exc
