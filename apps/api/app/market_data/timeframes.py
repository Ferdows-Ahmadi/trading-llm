from __future__ import annotations

from datetime import timedelta

from app.market_data.exceptions import UnsupportedTimeframeError

TIMEFRAME_TO_DELTA: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    try:
        return TIMEFRAME_TO_DELTA[timeframe]
    except KeyError as exc:
        raise UnsupportedTimeframeError(f"Unsupported timeframe: {timeframe}") from exc
