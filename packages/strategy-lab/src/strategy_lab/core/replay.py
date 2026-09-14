"""Causal replay snapshot orchestration for ACD Fast Scalp v0.1.

The orchestrator composes already-frozen infrastructure contracts. It does not
invent the unresolved momentum, confirmation, structural-swing, target, or ACD4
rules. Missing optional providers remain missing in the replay snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from collections.abc import Iterable

from .context import (
    AcdDirectionalContext,
    ExternalDirectionalContextSnapshot,
    bind_directional_context,
)
from .levels import ExternalAcdLevelSnapshot, bind_external_acd_levels
from .models import AcdLevels, SessionKind
from .opening_range import Candle, OpeningRange, compute_m1_opening_range
from .sessions import SessionWindow, build_session_window
from .timeframes import TimeframeBar, resample_completed_m1
from .trade_plan import ExternalTradePlanSnapshot, ValidatedTradePlan, bind_trade_plan

M1_DURATION = timedelta(minutes=1)


class ReplayPhase(StrEnum):
    PRE_SESSION = "pre_session"
    OR_FORMING = "or_forming"
    POST_OR = "post_or"


class ReplayDataError(ValueError):
    """Raised when a replay snapshot cannot be built causally."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReplayDataError(f"{field_name} must be timezone-aware")


def _visible_m1(candles: Iterable[Candle], *, decision_at: datetime) -> tuple[Candle, ...]:
    decision_utc = decision_at.astimezone(UTC)
    by_start: dict[datetime, Candle] = {}

    for candle in candles:
        start_utc = candle.started_at.astimezone(UTC)
        if start_utc + M1_DURATION > decision_utc:
            continue
        if start_utc in by_start:
            raise ReplayDataError(f"duplicate visible M1 candle: {start_utc.isoformat()}")
        by_start[start_utc] = candle

    return tuple(by_start[start] for start in sorted(by_start))


@dataclass(frozen=True, slots=True)
class AcdReplaySnapshot:
    """Everything the formalized ACD research layer knows at one replay instant."""

    instrument: str
    decision_at_utc: datetime
    phase: ReplayPhase
    session_window: SessionWindow
    visible_m1: tuple[Candle, ...]
    m5_bars: tuple[TimeframeBar, ...]
    m15_bars: tuple[TimeframeBar, ...]
    opening_range: OpeningRange | None
    acd_levels: AcdLevels | None
    directional_context: AcdDirectionalContext | None
    trade_plan: ValidatedTradePlan | None

    def __post_init__(self) -> None:
        if not self.instrument.strip():
            raise ReplayDataError("instrument must be recorded")
        _require_aware(self.decision_at_utc, field_name="decision_at_utc")


def build_acd_replay_snapshot(
    *,
    instrument: str,
    session: SessionKind,
    session_date: date,
    decision_at: datetime,
    candles: Iterable[Candle],
    m5_anchor_at: datetime,
    m15_anchor_at: datetime,
    display_timezone: str = "UTC",
    acd_level_snapshot: ExternalAcdLevelSnapshot | None = None,
    directional_context_snapshot: ExternalDirectionalContextSnapshot | None = None,
    trade_plan_snapshot: ExternalTradePlanSnapshot | None = None,
) -> AcdReplaySnapshot:
    """Build one chronological, no-lookahead ACD replay snapshot."""

    _require_aware(decision_at, field_name="decision_at")
    _require_aware(m5_anchor_at, field_name="m5_anchor_at")
    _require_aware(m15_anchor_at, field_name="m15_anchor_at")
    if not instrument.strip():
        raise ReplayDataError("instrument must be recorded")

    window = build_session_window(
        session,
        session_date,
        display_timezone=display_timezone,
    )
    decision_utc = decision_at.astimezone(UTC)

    if decision_utc < window.opens_at_utc:
        phase = ReplayPhase.PRE_SESSION
    elif decision_utc < window.opening_range_ends_at_utc:
        phase = ReplayPhase.OR_FORMING
    else:
        phase = ReplayPhase.POST_OR

    visible = _visible_m1(candles, decision_at=decision_at)
    m5_bars = resample_completed_m1(
        visible,
        timeframe_minutes=5,
        decision_at=decision_at,
        anchor_at=m5_anchor_at,
    )
    m15_bars = resample_completed_m1(
        visible,
        timeframe_minutes=15,
        decision_at=decision_at,
        anchor_at=m15_anchor_at,
    )

    opening_range: OpeningRange | None = None
    acd_levels: AcdLevels | None = None
    directional_context: AcdDirectionalContext | None = None
    trade_plan: ValidatedTradePlan | None = None

    if phase is ReplayPhase.POST_OR:
        opening_range = compute_m1_opening_range(visible, window)

        if acd_level_snapshot is not None:
            acd_levels = bind_external_acd_levels(
                acd_level_snapshot,
                window=window,
                opening_range=opening_range,
                decision_at=decision_at,
            )
        if directional_context_snapshot is not None:
            directional_context = bind_directional_context(
                directional_context_snapshot,
                window=window,
                decision_at=decision_at,
            )
        if trade_plan_snapshot is not None:
            trade_plan = bind_trade_plan(
                trade_plan_snapshot,
                window=window,
                decision_at=decision_at,
            )

    return AcdReplaySnapshot(
        instrument=instrument,
        decision_at_utc=decision_utc,
        phase=phase,
        session_window=window,
        visible_m1=visible,
        m5_bars=m5_bars,
        m15_bars=m15_bars,
        opening_range=opening_range,
        acd_levels=acd_levels,
        directional_context=directional_context,
        trade_plan=trade_plan,
    )
