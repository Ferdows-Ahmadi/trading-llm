from __future__ import annotations

from app.market_data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
from app.market_data.domain import OHLCVFetchRequest
from app.market_data.normalization import normalize_symbol
from app.market_data.resilience.cache import TtlCache
from app.market_data.resilience.executor import ResilienceExecutor
from app.market_data.resilience.rate_limit import InMemoryRateLimiter


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeHttpClient:
    def __init__(self, payload: dict[str, object], calls: dict[str, int]) -> None:
        self._payload = payload
        self._calls = calls

    def __enter__(self) -> "_FakeHttpClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        return None

    def get(self, url: str, params: dict[str, str]) -> _FakeResponse:
        self._calls["count"] += 1
        assert "function" in params
        return _FakeResponse(self._payload)


def test_alpha_vantage_adapter_fetches_and_caches() -> None:
    payload = {
        "Time Series FX (60min)": {
            "2025-01-01 00:00:00": {
                "1. open": "1.1000",
                "2. high": "1.1100",
                "3. low": "1.0900",
                "4. close": "1.1050",
            },
            "2025-01-01 01:00:00": {
                "1. open": "1.1050",
                "2. high": "1.1200",
                "3. low": "1.1000",
                "4. close": "1.1180",
            },
        }
    }
    calls = {"count": 0}
    resilience = ResilienceExecutor(
        cache=TtlCache(),
        rate_limiter=InMemoryRateLimiter(window_seconds=0.01),
        default_cache_ttl_seconds=60,
    )
    adapter = AlphaVantageAdapter(
        api_key="demo",
        resilience=resilience,
        http_client_factory=lambda: _FakeHttpClient(payload, calls),
        default_rate_limit_per_minute=100,
    )
    request = OHLCVFetchRequest(
        symbol=normalize_symbol("EURUSD", asset_class="forex"),
        timeframe="1h",
        limit=2,
    )

    candles_first = adapter.fetch_ohlcv(request)
    candles_second = adapter.fetch_ohlcv(request)

    assert len(candles_first) == 2
    assert float(candles_first[0].open) == 1.1
    assert float(candles_first[1].close) == 1.118
    assert float(candles_second[1].high) == 1.12
    assert calls["count"] == 1
