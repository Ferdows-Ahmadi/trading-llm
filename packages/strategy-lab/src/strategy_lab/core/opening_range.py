"""Opening Range reconstruction for ACD v0.1.

The v0.1 research path expects complete one-minute candles for the first
40 minutes of a session. Missing/duplicate bars are a data-quality failure,
not an invitation to guess the range.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Iterable

from .sessions import OPENING_RANGE_DURATION, SessionWindow

M1 = timedelta(minutes=1)
EXPECTED_M1_BARS = 40


class OpeningRangeDataError(ValueError):
    """Raised when the Opening Range cannot be reconstructed faithfully."""


@dataclass(frozen=True, slots=True)
class Candle:
    """Minimal OHLCV candle used by the strategy research layer."""

    started_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def __post_init__(self) -> None:
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("candle timestamp must be timezone-aware")

        prices = (self.open, self.high, self.low, self.close)
        if not all(isfinite(value) for value in prices):
            raise ValueError("candle OHLC values must be finite")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("candle high is inconsistent with OHLC values")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("candle low is inconsistent with OHLC values")
        if self.volume is not None and (not isfinite(self.volume) or self.volume < 0):
            raise ValueError("candle volume must be finite and non-negative when supplied")


@dataclass(frozen=True, slots=True)
class OpeningRange:
    starts_at_utc: datetime
    ends_at_utc: datetime
    high: float
    low: float
    candle_count: int


def compute_m1_opening_range(
    candles: Iterable[Candle],
    window: SessionWindow,
) -> OpeningRange:
    """Compute OR High/Low from exactly the expected 40 one-minute bars.

    Candles outside the frozen OR window are ignored. Every expected M1 start
    timestamp inside the window must be present exactly once.
    """

    if window.opening_range_ends_at_utc - window.opens_at_utc != OPENING_RANGE_DURATION:
        raise OpeningRangeDataError("session window does not contain a 40-minute Opening Range")

    expected_starts = tuple(
        window.opens_at_utc + (index * M1) for index in range(EXPECTED_M1_BARS)
    )
    expected_set = set(expected_starts)
    by_start: dict[datetime, Candle] = {}

    for candle in candles:
        started_at_utc = candle.started_at.astimezone(UTC)
        if started_at_utc not in expected_set:
            continue
        if started_at_utc in by_start:
            raise OpeningRangeDataError(
                f"duplicate M1 candle inside Opening Range: {started_at_utc.isoformat()}"
            )
        by_start[started_at_utc] = candle

    missing = [timestamp for timestamp in expected_starts if timestamp not in by_start]
    if missing:
        raise OpeningRangeDataError(
            f"Opening Range is incomplete: missing {len(missing)} of {EXPECTED_M1_BARS} M1 candles"
        )

    ordered = [by_start[timestamp] for timestamp in expected_starts]
    return OpeningRange(
        starts_at_utc=window.opens_at_utc,
        ends_at_utc=window.opening_range_ends_at_utc,
        high=max(candle.high for candle in ordered),
        low=min(candle.low for candle in ordered),
        candle_count=len(ordered),
    )
