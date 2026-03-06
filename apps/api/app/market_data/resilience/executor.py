from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from app.market_data.resilience.cache import TtlCache
from app.market_data.resilience.rate_limit import InMemoryRateLimiter
from app.market_data.resilience.retry import retry_call

T = TypeVar("T")


class ResilienceExecutor:
    """Applies cache, rate limiting, and retries around provider calls."""

    def __init__(
        self,
        cache: TtlCache[T],
        rate_limiter: InMemoryRateLimiter,
        *,
        default_cache_ttl_seconds: int = 30,
        default_max_attempts: int = 3,
        default_initial_backoff_seconds: float = 0.3,
        default_backoff_multiplier: float = 2.0,
        default_rate_limit_per_minute: int = 60,
    ) -> None:
        self._cache = cache
        self._rate_limiter = rate_limiter
        self._default_cache_ttl_seconds = default_cache_ttl_seconds
        self._default_max_attempts = default_max_attempts
        self._default_initial_backoff_seconds = default_initial_backoff_seconds
        self._default_backoff_multiplier = default_backoff_multiplier
        self._default_rate_limit_per_minute = default_rate_limit_per_minute

    def execute(
        self,
        *,
        provider_code: str,
        cache_key: str,
        operation: Callable[[], T],
        cache_ttl_seconds: int | None = None,
        max_attempts: int | None = None,
        initial_backoff_seconds: float | None = None,
        backoff_multiplier: float | None = None,
        rate_limit_per_minute: int | None = None,
        retry_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> T:
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        self._rate_limiter.acquire(
            provider_code=provider_code,
            limit_per_window=rate_limit_per_minute or self._default_rate_limit_per_minute,
        )

        result = retry_call(
            operation,
            max_attempts=max_attempts or self._default_max_attempts,
            initial_delay_seconds=(
                initial_backoff_seconds or self._default_initial_backoff_seconds
            ),
            backoff_multiplier=backoff_multiplier or self._default_backoff_multiplier,
            retry_exceptions=retry_exceptions,
        )
        self._cache.set(
            cache_key,
            result,
            ttl_seconds=cache_ttl_seconds or self._default_cache_ttl_seconds,
        )
        return result
