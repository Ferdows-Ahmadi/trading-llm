from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from app.market_data.adapters.base import MarketDataAdapter
from app.market_data.domain import OHLCVCandle, OHLCVFetchRequest
from app.market_data.exceptions import ProviderRequestError
from app.market_data.normalization import provider_symbol_for
from app.market_data.resilience.executor import ResilienceExecutor
from app.market_data.timeframes import timeframe_to_timedelta


class CcxtExchange(Protocol):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[Any]]:
        ...


class CcxtAdapter(MarketDataAdapter):
    provider_code = "ccxt"

    def __init__(
        self,
        resilience: ResilienceExecutor[list[OHLCVCandle]],
        *,
        exchange_id: str = "binance",
        exchange_factory: Callable[[str], CcxtExchange] | None = None,
        default_rate_limit_per_minute: int = 60,
        default_cache_ttl_seconds: int = 20,
    ) -> None:
        self._resilience = resilience
        self._exchange_id = exchange_id
        self._exchange_factory = exchange_factory or self._build_exchange
        self._default_rate_limit_per_minute = default_rate_limit_per_minute
        self._default_cache_ttl_seconds = default_cache_ttl_seconds

    def fetch_ohlcv(self, request: OHLCVFetchRequest) -> list[OHLCVCandle]:
        provider_symbol = provider_symbol_for(self.provider_code, request.symbol)
        since_ms = int(request.since.timestamp() * 1000) if request.since is not None else None
        cache_key = (
            f"{self.provider_code}:{self._exchange_id}:{provider_symbol}:"
            f"{request.timeframe}:{request.limit}:{since_ms}"
        )

        def _call_provider() -> list[OHLCVCandle]:
            exchange = self._exchange_factory(self._exchange_id)
            try:
                rows = exchange.fetch_ohlcv(
                    provider_symbol, timeframe=request.timeframe, since=since_ms, limit=request.limit
                )
            except Exception as exc:  # pragma: no cover - vendor-specific exceptions
                raise ProviderRequestError(f"CCXT fetch_ohlcv failed: {exc}") from exc
            return self._rows_to_candles(rows, timeframe=request.timeframe)

        return self._resilience.execute(
            provider_code=self.provider_code,
            cache_key=cache_key,
            operation=_call_provider,
            cache_ttl_seconds=self._default_cache_ttl_seconds,
            rate_limit_per_minute=self._default_rate_limit_per_minute,
            retry_exceptions=(ProviderRequestError,),
        )

    @staticmethod
    def _rows_to_candles(rows: list[list[Any]], timeframe: str) -> list[OHLCVCandle]:
        candles: list[OHLCVCandle] = []
        interval = timeframe_to_timedelta(timeframe)
        for row in rows:
            if len(row) < 6:
                continue
            open_time = datetime.fromtimestamp(float(row[0]) / 1000.0, tz=UTC)
            candles.append(
                OHLCVCandle(
                    open_time=open_time,
                    close_time=open_time + interval,
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])) if row[5] is not None else None,
                )
            )
        return candles

    @staticmethod
    def _build_exchange(exchange_id: str) -> CcxtExchange:
        try:
            import ccxt  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ProviderRequestError("ccxt is not installed") from exc

        try:
            exchange_class = getattr(ccxt, exchange_id)
        except AttributeError as exc:
            raise ProviderRequestError(f"CCXT exchange not found: {exchange_id}") from exc

        return exchange_class({"enableRateLimit": False, "timeout": 10000})
