from __future__ import annotations

from app.market_data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
from app.market_data.adapters.base import MarketDataAdapter
from app.market_data.adapters.ccxt_adapter import CcxtAdapter
from app.market_data.domain import OHLCVCandle
from app.market_data.exceptions import ProviderNotFoundError
from app.market_data.resilience.cache import TtlCache
from app.market_data.resilience.executor import ResilienceExecutor
from app.market_data.resilience.rate_limit import InMemoryRateLimiter


class AdapterRegistry:
    def __init__(self, adapters: list[MarketDataAdapter]) -> None:
        self._adapters = {adapter.provider_code: adapter for adapter in adapters}

    def get(self, provider_code: str) -> MarketDataAdapter:
        adapter = self._adapters.get(provider_code)
        if adapter is None:
            raise ProviderNotFoundError(f"Provider adapter not found: {provider_code}")
        return adapter

    def provider_codes(self) -> list[str]:
        return sorted(self._adapters.keys())


def build_default_registry(
    *,
    alpha_vantage_api_key: str,
    ccxt_exchange_id: str,
    cache_ttl_seconds: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
) -> AdapterRegistry:
    cache = TtlCache[list[OHLCVCandle]]()
    limiter = InMemoryRateLimiter(window_seconds=60.0)
    resilience = ResilienceExecutor[list[OHLCVCandle]](
        cache=cache,
        rate_limiter=limiter,
        default_cache_ttl_seconds=cache_ttl_seconds,
        default_max_attempts=retry_attempts,
        default_initial_backoff_seconds=retry_backoff_seconds,
        default_backoff_multiplier=2.0,
    )

    adapters: list[MarketDataAdapter] = [
        CcxtAdapter(
            resilience=resilience,
            exchange_id=ccxt_exchange_id,
            default_cache_ttl_seconds=cache_ttl_seconds,
        )
    ]
    if alpha_vantage_api_key:
        adapters.append(
            AlphaVantageAdapter(
                api_key=alpha_vantage_api_key,
                resilience=resilience,
                default_cache_ttl_seconds=cache_ttl_seconds,
            )
        )

    return AdapterRegistry(adapters=adapters)
