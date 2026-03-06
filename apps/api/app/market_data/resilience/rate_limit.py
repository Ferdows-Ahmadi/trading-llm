from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by provider code."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def acquire(self, provider_code: str, limit_per_window: int) -> None:
        if limit_per_window <= 0:
            return

        while True:
            sleep_for = 0.0
            now = time.monotonic()
            with self._lock:
                bucket = self._events[provider_code]
                while bucket and now - bucket[0] >= self._window_seconds:
                    bucket.popleft()

                if len(bucket) < limit_per_window:
                    bucket.append(now)
                    return

                sleep_for = self._window_seconds - (now - bucket[0])

            if sleep_for > 0:
                time.sleep(sleep_for)
