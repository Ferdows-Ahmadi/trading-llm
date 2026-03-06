from __future__ import annotations

from app.market_data.resilience.cache import TtlCache
from app.market_data.resilience.executor import ResilienceExecutor
from app.market_data.resilience.rate_limit import InMemoryRateLimiter
from app.news_context.adapters.alpha_vantage_news_adapter import AlphaVantageNewsAdapter
from app.news_context.adapters.base import NewsProviderAdapter
from app.news_context.domain import NewsCandidate
from app.news_context.exceptions import NewsProviderNotFoundError


class NewsAdapterRegistry:
    def __init__(self, adapters: list[NewsProviderAdapter]) -> None:
        self._adapters = {adapter.provider_code: adapter for adapter in adapters}

    def get(self, provider_code: str) -> NewsProviderAdapter:
        adapter = self._adapters.get(provider_code)
        if adapter is None:
            raise NewsProviderNotFoundError(f"News provider adapter not found: {provider_code}")
        return adapter

    def provider_codes(self) -> list[str]:
        return sorted(self._adapters.keys())


def build_news_registry(
    *,
    alpha_vantage_api_key: str,
    cache_ttl_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
) -> NewsAdapterRegistry:
    cache = TtlCache[list[NewsCandidate]]()
    limiter = InMemoryRateLimiter(window_seconds=60.0)
    resilience = ResilienceExecutor[list[NewsCandidate]](
        cache=cache,
        rate_limiter=limiter,
        default_cache_ttl_seconds=cache_ttl_seconds,
        default_max_attempts=retry_attempts,
        default_initial_backoff_seconds=retry_backoff_seconds,
        default_backoff_multiplier=2.0,
    )
    adapters: list[NewsProviderAdapter] = []
    if alpha_vantage_api_key:
        adapters.append(
            AlphaVantageNewsAdapter(
                api_key=alpha_vantage_api_key,
                resilience=resilience,
                default_cache_ttl_seconds=cache_ttl_seconds,
            )
        )
    return NewsAdapterRegistry(adapters=adapters)
