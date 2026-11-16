"""Retry helper for transient network errors, plus the expected-abort exception."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


class Abort(Exception):
    """Expected stop (quality gate, quota, auth). Workflows end as success with 'ABORTED: reason'."""


def retry(fn: Callable[[], T], attempts: int = 3, base_delay: float = 2.0,
          retry_on: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError)) -> T:
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as e:  # noqa: PERF203
            last = e
            if i < attempts - 1:
                time.sleep(base_delay * (2 ** i))
    assert last is not None
    raise last
