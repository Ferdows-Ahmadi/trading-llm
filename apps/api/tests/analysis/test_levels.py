from datetime import UTC, datetime, timedelta

from app.analysis.indicators import candles_to_frame, compute_indicators
from app.analysis.levels import detect_support_resistance
from app.repositories.market_data_repository import CandleRecord


def test_support_resistance_detects_levels() -> None:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    candles: list[CandleRecord] = []
    price = 100.0
    for idx in range(140):
        phase = idx % 10
        close = 106.0 if phase in (1, 2) else 94.0 if phase in (6, 7) else price + 0.2
        high = max(price, close) + 0.6
        low = min(price, close) - 0.6
        candles.append(
            CandleRecord(
                symbol="BTCUSDT",
                timeframe="1h",
                provider_code="ccxt",
                open_time=base + timedelta(hours=idx),
                close_time=base + timedelta(hours=idx + 1),
                open=price,
                high=high,
                low=low,
                close=close,
                volume=1200.0 + idx,
            )
        )
        price = close

    indicators = compute_indicators(candles_to_frame(candles))
    supports, resistances = detect_support_resistance(indicators)

    assert len(supports) >= 1
    assert len(resistances) >= 1
    assert supports[0].level < float(indicators.iloc[-1]["close"])
    assert resistances[0].level > float(indicators.iloc[-1]["close"])
