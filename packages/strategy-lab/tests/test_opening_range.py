from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_lab.core.models import SessionKind
from strategy_lab.core.opening_range import (
    Candle,
    OpeningRangeDataError,
    compute_m1_opening_range,
)
from strategy_lab.core.sessions import SessionWindow, build_session_window


def _window() -> SessionWindow:
    return build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )


def _complete_or_candles() -> list[Candle]:
    window = _window()
    candles: list[Candle] = []
    for index in range(40):
        started = window.opens_at_utc + timedelta(minutes=index)
        base = 100.0 + index
        candles.append(
            Candle(
                started_at=started,
                open=base,
                high=base + 2.0,
                low=base - 3.0,
                close=base + 1.0,
            )
        )
    return candles


def test_compute_opening_range_uses_exact_first_40_minutes() -> None:
    window = _window()
    candles = _complete_or_candles()

    candles.append(
        Candle(
            started_at=window.opening_range_ends_at_utc,
            open=1000.0,
            high=5000.0,
            low=1.0,
            close=4000.0,
        )
    )

    opening_range = compute_m1_opening_range(candles, window)

    assert opening_range.candle_count == 40
    assert opening_range.high == 141.0
    assert opening_range.low == 97.0


def test_missing_or_candle_is_rejected() -> None:
    candles = _complete_or_candles()
    del candles[17]

    with pytest.raises(OpeningRangeDataError, match="missing 1 of 40"):
        compute_m1_opening_range(candles, _window())


def test_duplicate_or_candle_is_rejected() -> None:
    candles = _complete_or_candles()
    candles.append(candles[5])

    with pytest.raises(OpeningRangeDataError, match="duplicate M1 candle"):
        compute_m1_opening_range(candles, _window())


def test_candle_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Candle(
            started_at=datetime(2026, 9, 14, 13, 30),  # noqa: DTZ001 - intentional invalid input
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
        )


def test_timezone_aware_candle_is_accepted() -> None:
    candle = Candle(
        started_at=datetime(2026, 9, 14, 13, 30, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )

    assert candle.started_at.tzinfo is UTC
