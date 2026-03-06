from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market_data.adapters.base import MarketDataAdapter
from app.market_data.adapters.registry import AdapterRegistry
from app.market_data.domain import OHLCVCandle, OHLCVFetchRequest
from app.market_data.service import MarketDataService
from app.repositories.market_data_repository import AssetRecord, CandleRecord, ProviderRecord


class _FakeAdapter(MarketDataAdapter):
    provider_code = "ccxt"

    def fetch_ohlcv(self, request: OHLCVFetchRequest) -> list[OHLCVCandle]:
        open_time = datetime(2025, 1, 1, tzinfo=UTC)
        return [
            OHLCVCandle(
                open_time=open_time,
                close_time=open_time + timedelta(hours=1),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("10"),
            )
        ]


class _FakeRepository:
    def __init__(self) -> None:
        self.saved_candles: list[OHLCVCandle] = []

    def get_or_create_provider(self, provider_code: str) -> ProviderRecord:
        return ProviderRecord(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            code=provider_code,
            name="CCXT",
            rate_limit_per_minute=60,
        )

    def get_or_create_asset(self, symbol) -> AssetRecord:  # type: ignore[no-untyped-def]
        return AssetRecord(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            normalized_symbol=symbol.normalized_symbol,
            display_symbol=symbol.display_symbol,
            asset_class=symbol.asset_class,
            base_currency=symbol.base_currency,
            quote_currency=symbol.quote_currency,
        )

    def upsert_asset_provider_symbol(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    def upsert_candles(self, **kwargs) -> tuple[int, int]:  # type: ignore[no-untyped-def]
        self.saved_candles = kwargs["candles"]
        return (len(self.saved_candles), 0)

    def create_ingestion_run(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        return None

    def list_candles(self, **kwargs) -> list[CandleRecord]:  # type: ignore[no-untyped-def]
        return [
            CandleRecord(
                symbol="BTCUSDT",
                timeframe="1h",
                provider_code="ccxt",
                open_time=datetime(2025, 1, 1, tzinfo=UTC),
                close_time=datetime(2025, 1, 1, 1, tzinfo=UTC),
                open=100.0,
                high=110.0,
                low=90.0,
                close=105.0,
                volume=10.0,
            )
        ]


def test_market_data_service_ingests_ohlcv() -> None:
    repository = _FakeRepository()
    service = MarketDataService(repository=repository, registry=AdapterRegistry([_FakeAdapter()]))

    result = service.ingest_ohlcv(
        provider_code="ccxt",
        raw_symbol="BTC/USDT",
        timeframe="1h",
        limit=10,
        asset_class="crypto",
        since=None,
    )

    assert result.provider_code == "ccxt"
    assert result.normalized_symbol == "BTCUSDT"
    assert result.fetched_count == 1
    assert result.inserted_count == 1


def test_market_data_service_lists_stored_candles() -> None:
    repository = _FakeRepository()
    service = MarketDataService(repository=repository, registry=AdapterRegistry([_FakeAdapter()]))

    candles = service.list_candles(
        raw_symbol="BTCUSDT",
        timeframe="1h",
        limit=10,
        asset_class="crypto",
    )
    assert len(candles) == 1
    assert candles[0].symbol == "BTCUSDT"
