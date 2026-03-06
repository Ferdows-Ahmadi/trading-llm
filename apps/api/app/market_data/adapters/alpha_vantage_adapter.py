from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.market_data.adapters.base import MarketDataAdapter
from app.market_data.domain import OHLCVCandle, OHLCVFetchRequest
from app.market_data.exceptions import ProviderRequestError, UnsupportedTimeframeError
from app.market_data.resilience.executor import ResilienceExecutor
from app.market_data.timeframes import timeframe_to_timedelta

_BASE_URL = "https://www.alphavantage.co/query"
_SUPPORTED_FOREX_INTRADAY = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "60min"}


class AlphaVantageAdapter(MarketDataAdapter):
    provider_code = "alpha_vantage"

    def __init__(
        self,
        api_key: str,
        resilience: ResilienceExecutor[list[OHLCVCandle]],
        *,
        http_client_factory: Callable[[], httpx.Client] | None = None,
        default_rate_limit_per_minute: int = 5,
        default_cache_ttl_seconds: int = 60,
    ) -> None:
        if not api_key:
            raise ProviderRequestError("ALPHAVANTAGE_API_KEY is required for alpha_vantage adapter")
        self._api_key = api_key
        self._resilience = resilience
        self._http_client_factory = http_client_factory or self._default_http_client
        self._default_rate_limit_per_minute = default_rate_limit_per_minute
        self._default_cache_ttl_seconds = default_cache_ttl_seconds

    def fetch_ohlcv(self, request: OHLCVFetchRequest) -> list[OHLCVCandle]:
        params = self._build_params(request)
        cache_key = (
            f"{self.provider_code}:{request.symbol.normalized_symbol}:"
            f"{request.timeframe}:{request.limit}:{request.symbol.asset_class}"
        )

        def _call_provider() -> list[OHLCVCandle]:
            try:
                with self._http_client_factory() as client:
                    response = client.get(_BASE_URL, params=params)
                    response.raise_for_status()
            except Exception as exc:
                raise ProviderRequestError(f"Alpha Vantage request failed: {exc}") from exc

            payload = response.json()
            self._raise_for_provider_messages(payload)
            return self._payload_to_candles(payload, request)

        candles = self._resilience.execute(
            provider_code=self.provider_code,
            cache_key=cache_key,
            operation=_call_provider,
            cache_ttl_seconds=self._default_cache_ttl_seconds,
            rate_limit_per_minute=self._default_rate_limit_per_minute,
            retry_exceptions=(ProviderRequestError,),
        )
        return candles[: request.limit]

    def _build_params(self, request: OHLCVFetchRequest) -> dict[str, str]:
        base = request.symbol.base_currency
        quote = request.symbol.quote_currency

        if request.symbol.asset_class == "forex":
            if request.timeframe == "1d":
                function_name = "FX_DAILY"
                return {
                    "function": function_name,
                    "from_symbol": base,
                    "to_symbol": quote,
                    "outputsize": "compact",
                    "apikey": self._api_key,
                }

            interval = _SUPPORTED_FOREX_INTRADAY.get(request.timeframe)
            if interval is None:
                raise UnsupportedTimeframeError(
                    f"Alpha Vantage forex supports {sorted(_SUPPORTED_FOREX_INTRADAY)} and 1d"
                )
            return {
                "function": "FX_INTRADAY",
                "from_symbol": base,
                "to_symbol": quote,
                "interval": interval,
                "outputsize": "compact",
                "apikey": self._api_key,
            }

        if request.symbol.asset_class == "crypto":
            if request.timeframe != "1d":
                raise UnsupportedTimeframeError("Alpha Vantage crypto adapter currently supports 1d only")
            return {
                "function": "DIGITAL_CURRENCY_DAILY",
                "symbol": base,
                "market": quote,
                "apikey": self._api_key,
            }

        raise ProviderRequestError(f"Unsupported asset class for alpha_vantage: {request.symbol.asset_class}")

    @staticmethod
    def _raise_for_provider_messages(payload: dict[str, Any]) -> None:
        for field in ("Error Message", "Information", "Note"):
            if field in payload:
                raise ProviderRequestError(f"Alpha Vantage error: {payload[field]}")

    @staticmethod
    def _payload_to_candles(payload: dict[str, Any], request: OHLCVFetchRequest) -> list[OHLCVCandle]:
        series = _extract_time_series(payload)
        interval = timeframe_to_timedelta(request.timeframe)
        candles: list[OHLCVCandle] = []

        for timestamp, raw_row in sorted(series.items()):
            open_time = _parse_timestamp(timestamp)
            row = {k.lower(): v for k, v in raw_row.items()}

            open_value = _extract_numeric_field(row, ("1. open", "1a. open", "open"))
            high_value = _extract_numeric_field(row, ("2. high", "2a. high", "high"))
            low_value = _extract_numeric_field(row, ("3. low", "3a. low", "low"))
            close_value = _extract_numeric_field(row, ("4. close", "4a. close", "close"))
            volume_value = _extract_optional_numeric_field(row, ("5. volume", "5. volume usd", "volume"))

            candles.append(
                OHLCVCandle(
                    open_time=open_time,
                    close_time=open_time + interval,
                    open=open_value,
                    high=high_value,
                    low=low_value,
                    close=close_value,
                    volume=volume_value,
                )
            )
        return candles

    @staticmethod
    def _default_http_client() -> httpx.Client:
        return httpx.Client(timeout=15.0)


def _extract_time_series(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    for key, value in payload.items():
        if key.lower().startswith("time series"):
            if isinstance(value, dict):
                return value
    raise ProviderRequestError("Alpha Vantage response did not include a time series payload")


def _parse_timestamp(value: str) -> datetime:
    if len(value) == 10:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _extract_numeric_field(row: dict[str, str], keys: tuple[str, ...]) -> Decimal:
    for key in keys:
        lowered = key.lower()
        if lowered in row:
            return Decimal(str(row[lowered]))
    for candidate_key, candidate_value in row.items():
        if any(token in candidate_key for token in ("open", "high", "low", "close")):
            if any(key.split()[-1] in candidate_key for key in keys):
                return Decimal(str(candidate_value))
    raise ProviderRequestError(f"Missing numeric field for keys: {keys}")


def _extract_optional_numeric_field(row: dict[str, str], keys: tuple[str, ...]) -> Decimal | None:
    for key in keys:
        lowered = key.lower()
        if lowered in row:
            return Decimal(str(row[lowered]))
    for candidate_key, candidate_value in row.items():
        if "volume" in candidate_key:
            return Decimal(str(candidate_value))
    return None
