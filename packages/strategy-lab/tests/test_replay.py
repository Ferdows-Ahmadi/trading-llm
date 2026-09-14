from datetime import date, timedelta

from strategy_lab.core.context import ExternalDirectionalContextSnapshot
from strategy_lab.core.levels import ExternalAcdLevelSnapshot
from strategy_lab.core.models import SessionKind, TrendDirection
from strategy_lab.core.opening_range import Candle
from strategy_lab.core.replay import ReplayPhase, build_acd_replay_snapshot
from strategy_lab.core.sessions import build_session_window
from strategy_lab.core.trade_plan import ExternalTradePlanSnapshot, TradePlanStatus, TradeSide

SESSION_DATE = date(2026, 9, 14)
SESSION = SessionKind.AMERICA_NEW_YORK


def _window():
    return build_session_window(SESSION, SESSION_DATE, display_timezone="UTC")


def _session_candles(count: int) -> list[Candle]:
    window = _window()
    candles: list[Candle] = []
    for index in range(count):
        base = 100.0 + (index * 0.01)
        candles.append(
            Candle(
                started_at=window.opens_at_utc + timedelta(minutes=index),
                open=base,
                high=base + 0.10,
                low=base - 0.10,
                close=base + 0.02,
                volume=float(index + 1),
            )
        )
    return candles


def _providers():
    window = _window()
    at = window.opening_range_ends_at_utc + timedelta(minutes=2)
    levels = ExternalAcdLevelSnapshot(
        session=SESSION,
        session_open_at=window.opens_at_utc,
        available_at=window.opening_range_ends_at_utc,
        a_up=101.0,
        c_up=102.0,
        a_down=99.0,
        c_down=98.0,
        source="acd_indicator",
        source_version="fixture-v1",
    )
    context = ExternalDirectionalContextSnapshot(
        session=SESSION,
        session_open_at=window.opens_at_utc,
        available_at=window.opening_range_ends_at_utc,
        previous_trend_observed_through=window.opens_at_utc - timedelta(minutes=1),
        m15_observed_through=window.opening_range_ends_at_utc,
        m5_observed_through=window.opening_range_ends_at_utc,
        previous_trend=TrendDirection.BULLISH,
        m15_direction=TrendDirection.BULLISH,
        m5_direction=TrendDirection.BULLISH,
        source="trader_annotation",
        source_version="fixture-v1",
    )
    trade_plan = ExternalTradePlanSnapshot(
        session=SESSION,
        session_open_at=window.opens_at_utc,
        observed_through=at,
        available_at=at,
        side=TradeSide.BUY,
        entry_price=100.0,
        structural_invalidation_price=95.0,
        target_price=110.0,
        source="trader_annotation",
        source_version="fixture-v1",
    )
    return levels, context, trade_plan


def test_pre_session_snapshot_has_no_opening_range() -> None:
    window = _window()
    snapshot = build_acd_replay_snapshot(
        instrument="XAUUSD",
        session=SESSION,
        session_date=SESSION_DATE,
        decision_at=window.opens_at_utc - timedelta(minutes=1),
        candles=_session_candles(45),
        m5_anchor_at=window.opens_at_utc,
        m15_anchor_at=window.opens_at_utc,
    )

    assert snapshot.phase is ReplayPhase.PRE_SESSION
    assert snapshot.opening_range is None
    assert snapshot.acd_levels is None
    assert snapshot.directional_context is None
    assert snapshot.trade_plan is None
    assert snapshot.visible_m1 == ()


def test_or_forming_snapshot_never_exposes_final_or() -> None:
    window = _window()
    snapshot = build_acd_replay_snapshot(
        instrument="XAUUSD",
        session=SESSION,
        session_date=SESSION_DATE,
        decision_at=window.opens_at_utc + timedelta(minutes=20),
        candles=_session_candles(45),
        m5_anchor_at=window.opens_at_utc,
        m15_anchor_at=window.opens_at_utc,
    )

    assert snapshot.phase is ReplayPhase.OR_FORMING
    assert snapshot.opening_range is None
    assert len(snapshot.visible_m1) == 20
    assert len(snapshot.m5_bars) == 4
    assert len(snapshot.m15_bars) == 1


def test_future_provider_snapshots_are_ignored_before_or_complete() -> None:
    window = _window()
    levels, context, trade_plan = _providers()
    kwargs = {
        "instrument": "XAUUSD",
        "session": SESSION,
        "session_date": SESSION_DATE,
        "decision_at": window.opens_at_utc + timedelta(minutes=20),
        "candles": _session_candles(45),
        "m5_anchor_at": window.opens_at_utc,
        "m15_anchor_at": window.opens_at_utc,
    }

    plain = build_acd_replay_snapshot(**kwargs)
    with_future_providers = build_acd_replay_snapshot(
        **kwargs,
        acd_level_snapshot=levels,
        directional_context_snapshot=context,
        trade_plan_snapshot=trade_plan,
    )

    assert plain == with_future_providers


def test_future_m1_candle_cannot_change_prior_snapshot() -> None:
    window = _window()
    decision_at = window.opens_at_utc + timedelta(minutes=20)
    base = _session_candles(45)
    future_outlier = Candle(
        started_at=window.opens_at_utc + timedelta(minutes=100),
        open=10_000.0,
        high=50_000.0,
        low=1.0,
        close=40_000.0,
        volume=1_000_000.0,
    )

    plain = build_acd_replay_snapshot(
        instrument="XAUUSD",
        session=SESSION,
        session_date=SESSION_DATE,
        decision_at=decision_at,
        candles=base,
        m5_anchor_at=window.opens_at_utc,
        m15_anchor_at=window.opens_at_utc,
    )
    with_future = build_acd_replay_snapshot(
        instrument="XAUUSD",
        session=SESSION,
        session_date=SESSION_DATE,
        decision_at=decision_at,
        candles=[*base, future_outlier],
        m5_anchor_at=window.opens_at_utc,
        m15_anchor_at=window.opens_at_utc,
    )

    assert plain == with_future


def test_post_or_snapshot_composes_all_available_contracts() -> None:
    window = _window()
    levels, context, trade_plan = _providers()
    decision_at = window.opening_range_ends_at_utc + timedelta(minutes=5)

    snapshot = build_acd_replay_snapshot(
        instrument="XAUUSD",
        session=SESSION,
        session_date=SESSION_DATE,
        decision_at=decision_at,
        candles=_session_candles(45),
        m5_anchor_at=window.opens_at_utc,
        m15_anchor_at=window.opens_at_utc,
        acd_level_snapshot=levels,
        directional_context_snapshot=context,
        trade_plan_snapshot=trade_plan,
    )

    assert snapshot.phase is ReplayPhase.POST_OR
    assert snapshot.opening_range is not None
    assert snapshot.opening_range.candle_count == 40
    assert snapshot.acd_levels is not None
    assert snapshot.acd_levels.source == "acd_indicator@fixture-v1"
    assert snapshot.directional_context is not None
    assert snapshot.directional_context.previous_trend is TrendDirection.BULLISH
    assert snapshot.trade_plan is not None
    assert snapshot.trade_plan.status is TradePlanStatus.ACCEPTED
    assert len(snapshot.visible_m1) == 45
    assert len(snapshot.m5_bars) == 9
    assert len(snapshot.m15_bars) == 3


def test_post_or_snapshot_allows_missing_optional_providers() -> None:
    window = _window()
    snapshot = build_acd_replay_snapshot(
        instrument="XAUUSD",
        session=SESSION,
        session_date=SESSION_DATE,
        decision_at=window.opening_range_ends_at_utc,
        candles=_session_candles(40),
        m5_anchor_at=window.opens_at_utc,
        m15_anchor_at=window.opens_at_utc,
    )

    assert snapshot.phase is ReplayPhase.POST_OR
    assert snapshot.opening_range is not None
    assert snapshot.acd_levels is None
    assert snapshot.directional_context is None
    assert snapshot.trade_plan is None
