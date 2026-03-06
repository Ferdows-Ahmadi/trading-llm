from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    max_attempts: int,
    initial_delay_seconds: float,
    backoff_multiplier: float,
    retry_exceptions: tuple[type[Exception], ...],
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    delay = initial_delay_seconds
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except retry_exceptions:
            if attempt >= max_attempts:
                raise
            time.sleep(delay)
            delay *= backoff_multiplier
