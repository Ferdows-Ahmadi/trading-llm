from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.repositories.market_data_repository import CandleRecord


def make_trending_candles(
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    count: int = 300,
    start_price: float = 100.0,
    drift: float = 0.25,
) -> list[CandleRecord]:
    base_time = datetime(2025, 1, 1, tzinfo=UTC)
    candles: list[CandleRecord] = []
    price = start_price
    for idx in range(count):
        wave = ((idx % 12) - 6) * 0.04
        open_price = price
        close_price = max(1.0, price + drift + wave)
        high_price = max(open_price, close_price) + 0.35
        low_price = min(open_price, close_price) - 0.35
        candles.append(
            CandleRecord(
                symbol=symbol,
                timeframe=timeframe,
                provider_code="ccxt",
                open_time=base_time + timedelta(hours=idx),
                close_time=base_time + timedelta(hours=idx + 1),
                open=round(open_price, 6),
                high=round(high_price, 6),
                low=round(low_price, 6),
                close=round(close_price, 6),
                volume=1500.0 + (idx * 3.0),
            )
        )
        price = close_price
    return candles
