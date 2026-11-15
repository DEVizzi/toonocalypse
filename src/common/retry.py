"""Retry helpers with exponential backoff and quota classification."""
from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class QuotaExceededError(RuntimeError):
    """Raised when an API returns 429 or daily quota is exhausted."""


def is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(tok in msg for tok in ("429", "quota", "resource_exhausted", "rate limit"))


def with_retry(
    fn: Callable[[], T],
    retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> T:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt == retries - 1:
                break
            delay = min(max_delay, base_delay * (2**attempt)) + random.uniform(0, 0.5)
            sleep_fn(delay)
    assert last_exc is not None
    if is_quota_error(last_exc):
        raise QuotaExceededError(str(last_exc)) from last_exc
    raise last_exc
