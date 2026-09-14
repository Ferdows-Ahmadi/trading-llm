from datetime import UTC, datetime, timedelta

import pytest

from strategy_lab.core.opening_range import Candle
from strategy_lab.core.timeframes import TimeframeDataError, resample_completed_m1

ANCHOR = datetime(2026, 9, 14, 13, 30, tzinfo=UTC)


def _candles(count: int, *, volume: bool = True) -> list[Candle]:
    result: list[Candle] = []
    for index in range(count):
        base = 100.0 + index
        result.append(
            Candle(
                started_at=ANCHOR + timedelta(minutes=index),
                open=base,
                high=base + 2.0,
                low=base - 1.0,
                close=base + 0.5,
                volume=float(index + 1) if volume else None,
            )
        )
    return result


def test_completed_m5_bar_aggregates_exact_constituents() -> None:
    bars = resample_completed_m1(
        _candles(5),
        timeframe_minutes=5,
        decision_at=ANCHOR + timedelta(minutes=5),
        anchor_at=ANCHOR,
    )

    assert len(bars) == 1
    bar = bars[0]
    assert bar.started_at_utc == ANCHOR
    assert bar.ended_at_utc == ANCHOR + timedelta(minutes=5)
    assert bar.open == 100.0
    assert bar.high == 106.0
    assert bar.low == 99.0
    assert bar.close == 104.5
    assert bar.volume == 15.0
    assert bar.source_candle_count == 5


def test_unfinished_m5_bucket_is_invisible() -> None:
    candles = _candles(9)
    bars = resample_completed_m1(
        candles,
        timeframe_minutes=5,
        decision_at=ANCHOR + timedelta(minutes=9),
        anchor_at=ANCHOR,
    )

    assert len(bars) == 1
    assert bars[0].ended_at_utc == ANCHOR + timedelta(minutes=5)


def test_future_candle_cannot_change_prior_snapshot() -> None:
    base = _candles(5)
    malicious_future = Candle(
        started_at=ANCHOR + timedelta(minutes=5),
        open=10_000.0,
        high=50_000.0,
        low=1.0,
        close=40_000.0,
        volume=1_000_000.0,
    )

    before = resample_completed_m1(
        base,
        timeframe_minutes=5,
        decision_at=ANCHOR + timedelta(minutes=5),
        anchor_at=ANCHOR,
    )
    after = resample_completed_m1(
        [*base, malicious_future],
        timeframe_minutes=5,
        decision_at=ANCHOR + timedelta(minutes=5),
        anchor_at=ANCHOR,
    )

    assert before == after


def test_completed_m15_bar_is_emitted_only_after_close() -> None:
    candles = _candles(15)

    before_close = resample_completed_m1(
        candles,
        timeframe_minutes=15,
        decision_at=ANCHOR + timedelta(minutes=14, seconds=59),
        anchor_at=ANCHOR,
    )
    at_close = resample_completed_m1(
        candles,
        timeframe_minutes=15,
        decision_at=ANCHOR + timedelta(minutes=15),
        anchor_at=ANCHOR,
    )

    assert before_close == ()
    assert len(at_close) == 1
    assert at_close[0].timeframe_minutes == 15


def test_missing_m1_inside_closed_bucket_is_rejected() -> None:
    candles = _candles(5)
    del candles[2]

    with pytest.raises(TimeframeDataError, match="incomplete"):
        resample_completed_m1(
            candles,
            timeframe_minutes=5,
            decision_at=ANCHOR + timedelta(minutes=5),
            anchor_at=ANCHOR,
        )


def test_duplicate_visible_m1_is_rejected() -> None:
    candles = _candles(5)
    candles.append(candles[1])

    with pytest.raises(TimeframeDataError, match="duplicate visible M1"):
        resample_completed_m1(
            candles,
            timeframe_minutes=5,
            decision_at=ANCHOR + timedelta(minutes=5),
            anchor_at=ANCHOR,
        )


def test_future_duplicate_does_not_affect_prior_decision() -> None:
    candles = _candles(6)
    candles.append(candles[5])

    bars = resample_completed_m1(
        candles,
        timeframe_minutes=5,
        decision_at=ANCHOR + timedelta(minutes=5),
        anchor_at=ANCHOR,
    )

    assert len(bars) == 1


def test_partial_volume_produces_unknown_aggregate_volume() -> None:
    candles = _candles(5)
    candle = candles[2]
    candles[2] = Candle(
        started_at=candle.started_at,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=None,
    )

    bars = resample_completed_m1(
        candles,
        timeframe_minutes=5,
        decision_at=ANCHOR + timedelta(minutes=5),
        anchor_at=ANCHOR,
    )

    assert bars[0].volume is None


def test_explicit_anchor_controls_bar_grid() -> None:
    shifted_anchor = ANCHOR + timedelta(minutes=2)
    candles = _candles(7)[2:7]

    bars = resample_completed_m1(
        candles,
        timeframe_minutes=5,
        decision_at=ANCHOR + timedelta(minutes=7),
        anchor_at=shifted_anchor,
    )

    assert len(bars) == 1
    assert bars[0].started_at_utc == shifted_anchor


def test_non_aligned_m1_timestamp_is_rejected() -> None:
    candle = Candle(
        started_at=ANCHOR + timedelta(seconds=30),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )

    with pytest.raises(TimeframeDataError, match="not aligned"):
        resample_completed_m1(
            [candle],
            timeframe_minutes=5,
            decision_at=ANCHOR + timedelta(minutes=5),
            anchor_at=ANCHOR,
        )
