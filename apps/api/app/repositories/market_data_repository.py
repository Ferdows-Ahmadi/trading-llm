from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.market_data.domain import OHLCVCandle, NormalizedSymbol
from app.models.market_data import Asset, AssetProviderSymbol, Candle, IngestionRun, Provider


@dataclass(frozen=True)
class ProviderRecord:
    id: uuid.UUID
    code: str
    name: str
    rate_limit_per_minute: int | None


@dataclass(frozen=True)
class AssetRecord:
    id: uuid.UUID
    normalized_symbol: str
    display_symbol: str
    asset_class: str
    base_currency: str
    quote_currency: str


@dataclass(frozen=True)
class CandleRecord:
    symbol: str
    timeframe: str
    provider_code: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None


class MarketDataRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get_or_create_provider(self, provider_code: str) -> ProviderRecord:
        with self._session_factory() as session:
            provider = session.scalar(select(Provider).where(Provider.code == provider_code))
            if provider is None:
                provider = Provider(
                    code=provider_code,
                    name=_provider_display_name(provider_code),
                    category="market_data",
                    is_enabled=True,
                )
                session.add(provider)
                session.commit()
                session.refresh(provider)

            return ProviderRecord(
                id=provider.id,
                code=provider.code,
                name=provider.name,
                rate_limit_per_minute=provider.rate_limit_per_minute,
            )

    def get_or_create_asset(self, symbol: NormalizedSymbol) -> AssetRecord:
        with self._session_factory() as session:
            asset = session.scalar(select(Asset).where(Asset.normalized_symbol == symbol.normalized_symbol))
            if asset is None:
                asset = Asset(
                    symbol=symbol.display_symbol,
                    normalized_symbol=symbol.normalized_symbol,
                    display_name=f"{symbol.base_currency} / {symbol.quote_currency}",
                    asset_class=symbol.asset_class,
                    base_currency=symbol.base_currency,
                    quote_currency=symbol.quote_currency,
                    is_active=True,
                )
                session.add(asset)
                session.commit()
                session.refresh(asset)
            return AssetRecord(
                id=asset.id,
                normalized_symbol=asset.normalized_symbol,
                display_symbol=asset.symbol,
                asset_class=asset.asset_class,
                base_currency=asset.base_currency,
                quote_currency=asset.quote_currency,
            )

    def upsert_asset_provider_symbol(
        self,
        *,
        asset_id: uuid.UUID,
        provider_id: uuid.UUID,
        provider_symbol: str,
    ) -> None:
        with self._session_factory() as session:
            existing = session.scalar(
                select(AssetProviderSymbol).where(
                    AssetProviderSymbol.asset_id == asset_id,
                    AssetProviderSymbol.provider_id == provider_id,
                    AssetProviderSymbol.provider_symbol == provider_symbol,
                )
            )
            if existing is None:
                session.add(
                    AssetProviderSymbol(
                        asset_id=asset_id,
                        provider_id=provider_id,
                        provider_symbol=provider_symbol,
                    )
                )
                session.commit()

    def upsert_candles(
        self,
        *,
        asset_id: uuid.UUID,
        provider_id: uuid.UUID,
        timeframe: str,
        candles: list[OHLCVCandle],
    ) -> tuple[int, int]:
        if not candles:
            return (0, 0)

        open_times = [candle.open_time for candle in candles]
        inserted = 0
        updated = 0

        with self._session_factory() as session:
            existing_query: Select[tuple[Candle]] = select(Candle).where(
                Candle.asset_id == asset_id,
                Candle.provider_id == provider_id,
                Candle.timeframe == timeframe,
                Candle.open_time.in_(open_times),
            )
            existing_rows = session.scalars(existing_query).all()
            existing_by_open_time = {row.open_time: row for row in existing_rows}

            for candle in candles:
                existing = existing_by_open_time.get(candle.open_time)
                if existing is None:
                    session.add(
                        Candle(
                            asset_id=asset_id,
                            provider_id=provider_id,
                            timeframe=timeframe,
                            open_time=candle.open_time,
                            close_time=candle.close_time,
                            open=candle.open,
                            high=candle.high,
                            low=candle.low,
                            close=candle.close,
                            volume=candle.volume,
                            quote_volume=candle.quote_volume,
                            trade_count=candle.trade_count,
                        )
                    )
                    inserted += 1
                    continue

                if _candle_changed(existing, candle):
                    existing.close_time = candle.close_time
                    existing.open = candle.open
                    existing.high = candle.high
                    existing.low = candle.low
                    existing.close = candle.close
                    existing.volume = candle.volume
                    existing.quote_volume = candle.quote_volume
                    existing.trade_count = candle.trade_count
                    updated += 1

            session.commit()

        return (inserted, updated)

    def create_ingestion_run(
        self,
        *,
        provider_id: uuid.UUID,
        run_type: str,
        status: str,
        details: dict[str, object],
    ) -> None:
        with self._session_factory() as session:
            started_at = datetime.now(tz=UTC)
            session.add(
                IngestionRun(
                    provider_id=provider_id,
                    run_type=run_type,
                    status=status,
                    started_at=started_at,
                    finished_at=datetime.now(tz=UTC),
                    details=details,
                )
            )
            session.commit()

    def list_candles(
        self,
        *,
        normalized_symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[CandleRecord]:
        with self._session_factory() as session:
            query = (
                select(Candle, Asset.normalized_symbol, Provider.code)
                .join(Asset, Candle.asset_id == Asset.id)
                .join(Provider, Candle.provider_id == Provider.id)
                .where(Asset.normalized_symbol == normalized_symbol, Candle.timeframe == timeframe)
                .order_by(Candle.open_time.desc())
                .limit(limit)
            )

            rows = session.execute(query).all()
            candles = [
                CandleRecord(
                    symbol=row[1],
                    timeframe=row[0].timeframe,
                    provider_code=row[2],
                    open_time=row[0].open_time,
                    close_time=row[0].close_time,
                    open=float(row[0].open),
                    high=float(row[0].high),
                    low=float(row[0].low),
                    close=float(row[0].close),
                    volume=float(row[0].volume) if row[0].volume is not None else None,
                )
                for row in rows
            ]
            return list(reversed(candles))


def _provider_display_name(provider_code: str) -> str:
    display_names = {
        "ccxt": "CCXT",
        "alpha_vantage": "Alpha Vantage",
    }
    return display_names.get(provider_code, provider_code.upper())


def _candle_changed(existing: Candle, incoming: OHLCVCandle) -> bool:
    return any(
        (
            existing.close_time != incoming.close_time,
            existing.open != incoming.open,
            existing.high != incoming.high,
            existing.low != incoming.low,
            existing.close != incoming.close,
            existing.volume != incoming.volume,
            existing.quote_volume != incoming.quote_volume,
            existing.trade_count != incoming.trade_count,
        )
    )
