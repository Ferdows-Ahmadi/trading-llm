from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import cast

from app.core.config import settings
from app.market_data.adapters.registry import AdapterRegistry, build_default_registry
from app.market_data.domain import AssetClass, OHLCVFetchRequest
from app.market_data.normalization import normalize_symbol, provider_symbol_for
from app.repositories.base import SessionLocal
from app.repositories.market_data_repository import CandleRecord, MarketDataRepository


@dataclass(frozen=True)
class IngestionSummary:
    provider_code: str
    normalized_symbol: str
    timeframe: str
    fetched_count: int
    inserted_count: int
    updated_count: int
    duration_ms: int


class MarketDataService:
    def __init__(self, repository: MarketDataRepository, registry: AdapterRegistry) -> None:
        self._repository = repository
        self._registry = registry

    def ingest_ohlcv(
        self,
        *,
        provider_code: str,
        raw_symbol: str,
        timeframe: str,
        limit: int,
        asset_class: str | None,
        since: datetime | None,
    ) -> IngestionSummary:
        started = perf_counter()
        typed_asset_class = cast(AssetClass | None, asset_class)
        symbol = normalize_symbol(raw_symbol, asset_class=typed_asset_class)
        provider = self._repository.get_or_create_provider(provider_code)
        try:
            adapter = self._registry.get(provider_code)
            request = OHLCVFetchRequest(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                since=since,
            )
            candles = adapter.fetch_ohlcv(request)
            asset = self._repository.get_or_create_asset(symbol)
            self._repository.upsert_asset_provider_symbol(
                asset_id=asset.id,
                provider_id=provider.id,
                provider_symbol=provider_symbol_for(provider_code, symbol),
            )
            inserted_count, updated_count = self._repository.upsert_candles(
                asset_id=asset.id,
                provider_id=provider.id,
                timeframe=timeframe,
                candles=candles,
            )
            duration_ms = int((perf_counter() - started) * 1000)
            self._repository.create_ingestion_run(
                provider_id=provider.id,
                run_type="ohlcv_ingestion",
                status="success",
                details={
                    "provider_code": provider_code,
                    "symbol": symbol.normalized_symbol,
                    "timeframe": timeframe,
                    "fetched_count": len(candles),
                    "inserted_count": inserted_count,
                    "updated_count": updated_count,
                    "duration_ms": duration_ms,
                },
            )
            return IngestionSummary(
                provider_code=provider_code,
                normalized_symbol=symbol.normalized_symbol,
                timeframe=timeframe,
                fetched_count=len(candles),
                inserted_count=inserted_count,
                updated_count=updated_count,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((perf_counter() - started) * 1000)
            self._repository.create_ingestion_run(
                provider_id=provider.id,
                run_type="ohlcv_ingestion",
                status="failed",
                details={
                    "provider_code": provider_code,
                    "symbol": symbol.normalized_symbol,
                    "timeframe": timeframe,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
            )
            raise

    def list_candles(
        self,
        *,
        raw_symbol: str,
        timeframe: str,
        limit: int,
        asset_class: str | None,
    ) -> list[CandleRecord]:
        typed_asset_class = cast(AssetClass | None, asset_class)
        symbol = normalize_symbol(raw_symbol, asset_class=typed_asset_class)
        return self._repository.list_candles(
            normalized_symbol=symbol.normalized_symbol,
            timeframe=timeframe,
            limit=limit,
        )

    def available_providers(self) -> list[str]:
        return self._registry.provider_codes()


_service_instance: MarketDataService | None = None


def get_market_data_service() -> MarketDataService:
    global _service_instance
    if _service_instance is None:
        repository = MarketDataRepository(session_factory=SessionLocal)
        registry = build_default_registry(
            alpha_vantage_api_key=settings.alpha_vantage_api_key,
            ccxt_exchange_id=settings.ccxt_exchange_id,
            cache_ttl_seconds=settings.market_data_cache_ttl_seconds,
            retry_attempts=settings.market_data_retry_attempts,
            retry_backoff_seconds=settings.market_data_retry_backoff_seconds,
        )
        _service_instance = MarketDataService(repository=repository, registry=registry)
    return _service_instance


def reset_market_data_service_for_tests() -> None:
    global _service_instance
    _service_instance = None
