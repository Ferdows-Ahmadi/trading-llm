from __future__ import annotations

from datetime import UTC, datetime

from app.market_data.adapters.ccxt_adapter import CcxtAdapter
from app.market_data.domain import OHLCVFetchRequest
from app.market_data.normalization import normalize_symbol
from app.market_data.resilience.cache import TtlCache
from app.market_data.resilience.executor import ResilienceExecutor
from app.market_data.resilience.rate_limit import InMemoryRateLimiter


class _FakeExchange:
    def __init__(self) -> None:
        self.calls = 0

    def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[list[float]]:
        self.calls += 1
        assert symbol == "BTC/USDT"
        assert timeframe == "1h"
        assert limit == 2
        return [
            [1735689600000, 100.0, 110.0, 90.0, 105.0, 12.0],
            [1735693200000, 105.0, 112.0, 100.0, 111.0, 18.0],
        ]


def test_ccxt_adapter_fetches_and_caches() -> None:
    fake_exchange = _FakeExchange()
    resilience = ResilienceExecutor(
        cache=TtlCache(),
        rate_limiter=InMemoryRateLimiter(window_seconds=0.01),
        default_cache_ttl_seconds=60,
    )
    adapter = CcxtAdapter(
        resilience=resilience,
        exchange_factory=lambda _: fake_exchange,
        default_rate_limit_per_minute=100,
    )
    request = OHLCVFetchRequest(
        symbol=normalize_symbol("BTCUSDT", asset_class="crypto"),
        timeframe="1h",
        limit=2,
        since=datetime(2025, 1, 1, tzinfo=UTC),
    )

    candles_first = adapter.fetch_ohlcv(request)
    candles_second = adapter.fetch_ohlcv(request)

    assert len(candles_first) == 2
    assert candles_first[0].open == 100
    assert candles_first[0].close == 105
    assert candles_second[1].high == 112
    assert fake_exchange.calls == 1
