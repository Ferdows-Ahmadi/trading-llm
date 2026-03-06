from __future__ import annotations

import time

from app.market_data.resilience.cache import TtlCache
from app.market_data.resilience.rate_limit import InMemoryRateLimiter
from app.market_data.resilience.retry import retry_call


def test_retry_call_retries_then_succeeds() -> None:
    attempts = {"count": 0}

    def flaky_call() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError("retry")
        return "ok"

    result = retry_call(
        flaky_call,
        max_attempts=3,
        initial_delay_seconds=0.01,
        backoff_multiplier=1.0,
        retry_exceptions=(ValueError,),
    )
    assert result == "ok"
    assert attempts["count"] == 3


def test_ttl_cache_expires() -> None:
    cache: TtlCache[int] = TtlCache()
    cache.set("k", 10, ttl_seconds=1)
    assert cache.get("k") == 10

    cache.set("x", 11, ttl_seconds=0)
    assert cache.get("x") is None


def test_rate_limiter_throttles() -> None:
    limiter = InMemoryRateLimiter(window_seconds=0.08)
    limiter.acquire("ccxt", limit_per_window=1)

    started = time.perf_counter()
    limiter.acquire("ccxt", limit_per_window=1)
    elapsed = time.perf_counter() - started

    assert elapsed >= 0.07
