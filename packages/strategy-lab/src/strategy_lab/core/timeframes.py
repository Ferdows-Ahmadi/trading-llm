"""Chronological M1 -> higher-timeframe resampling for strategy replay.

Only source candles that are fully closed at `decision_at` may contribute. A
higher-timeframe bar is emitted only after its own close and only when every
expected M1 candle in that bucket is present exactly once.

The caller supplies the grid anchor explicitly. This avoids silently choosing a
broker/session candle alignment that the strategy source has not specified.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from .opening_range import Candle

M1_DURATION = timedelta(minutes=1)


class TimeframeDataError(ValueError):
    """Raised when deterministic higher-timeframe reconstruction is unsafe."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeframeDataError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class TimeframeBar:
    """One completed OHLCV bar reconstructed from exact M1 constituents."""

    started_at_utc: datetime
    ended_at_utc: datetime
    timeframe_minutes: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source_candle_count: int

    def __post_init__(self) -> None:
        _require_aware(self.started_at_utc, field_name="started_at_utc")
        _require_aware(self.ended_at_utc, field_name="ended_at_utc")
        if self.timeframe_minutes <= 1:
            raise TimeframeDataError("higher timeframe must be greater than one minute")
        if self.ended_at_utc <= self.started_at_utc:
            raise TimeframeDataError("timeframe bar end must be after its start")
        if self.source_candle_count != self.timeframe_minutes:
            raise TimeframeDataError(
                "timeframe bar must contain exactly one M1 candle per minute"
            )
        prices = (self.open, self.high, self.low, self.close)
        if not all(isfinite(value) for value in prices):
            raise TimeframeDataError("timeframe bar OHLC values must be finite")


def resample_completed_m1(
    candles: Iterable[Candle],
    *,
    timeframe_minutes: int,
    decision_at: datetime,
    anchor_at: datetime,
) -> tuple[TimeframeBar, ...]:
    """Build completed higher-timeframe bars known at `decision_at`.

    `anchor_at` defines the higher-timeframe grid. For example, callers can use
    an exchange/provider bar anchor or a session-specific anchor. The function
    does not guess which alignment is scientifically correct.
    """

    _require_aware(decision_at, field_name="decision_at")
    _require_aware(anchor_at, field_name="anchor_at")
    if timeframe_minutes <= 1:
        raise TimeframeDataError("timeframe_minutes must be greater than one")

    decision_utc = decision_at.astimezone(UTC)
    anchor_utc = anchor_at.astimezone(UTC)
    timeframe = timedelta(minutes=timeframe_minutes)

    visible_by_start: dict[datetime, Candle] = {}
    for candle in candles:
        start_utc = candle.started_at.astimezone(UTC)
        candle_end_utc = start_utc + M1_DURATION

        # Future/still-forming M1 data is invisible to this replay instant.
        if candle_end_utc > decision_utc:
            continue

        minute_offset = (start_utc - anchor_utc).total_seconds() / 60.0
        if not minute_offset.is_integer():
            raise TimeframeDataError(
                "M1 candle timestamp is not aligned to the supplied one-minute grid"
            )
        if start_utc in visible_by_start:
            raise TimeframeDataError(
                f"duplicate visible M1 candle: {start_utc.isoformat()}"
            )
        visible_by_start[start_utc] = candle

    grouped: dict[datetime, list[tuple[datetime, Candle]]] = defaultdict(list)
    for start_utc, candle in visible_by_start.items():
        minute_offset = int((start_utc - anchor_utc).total_seconds() // 60)
        bucket_index = minute_offset // timeframe_minutes
        bucket_start = anchor_utc + (bucket_index * timeframe)
        bucket_end = bucket_start + timeframe
        if bucket_end <= decision_utc:
            grouped[bucket_start].append((start_utc, candle))

    bars: list[TimeframeBar] = []
    for bucket_start in sorted(grouped):
        bucket_end = bucket_start + timeframe
        expected_starts = tuple(
            bucket_start + timedelta(minutes=index)
            for index in range(timeframe_minutes)
        )
        by_start = {start: candle for start, candle in grouped[bucket_start]}
        missing = [start for start in expected_starts if start not in by_start]
        if missing:
            raise TimeframeDataError(
                f"closed {timeframe_minutes}m bucket starting "
                f"{bucket_start.isoformat()} is incomplete: missing "
                f"{len(missing)} of {timeframe_minutes} M1 candles"
            )

        ordered = [by_start[start] for start in expected_starts]
        volumes = [candle.volume for candle in ordered]
        volume = None
        if all(value is not None for value in volumes):
            volume = sum(value for value in volumes if value is not None)

        bars.append(
            TimeframeBar(
                started_at_utc=bucket_start,
                ended_at_utc=bucket_end,
                timeframe_minutes=timeframe_minutes,
                open=ordered[0].open,
                high=max(candle.high for candle in ordered),
                low=min(candle.low for candle in ordered),
                close=ordered[-1].close,
                volume=volume,
                source_candle_count=len(ordered),
            )
        )

    return tuple(bars)
