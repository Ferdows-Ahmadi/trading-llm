from datetime import date, timedelta

import pytest

from strategy_lab.core.models import SessionKind
from strategy_lab.core.sessions import SessionWindow, build_session_window
from strategy_lab.core.trade_plan import (
    ExitManagement,
    ExternalTradePlanSnapshot,
    TradePlanDataError,
    TradePlanStatus,
    TradeSide,
    bind_trade_plan,
)


def _window() -> SessionWindow:
    return build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )


def _snapshot(
    *,
    side: TradeSide = TradeSide.BUY,
    entry_price: float = 100.0,
    stop_price: float = 95.0,
    target_price: float = 110.0,
    observed_offset_minutes: int = 41,
    available_offset_minutes: int = 41,
    session: SessionKind | None = None,
    session_open_offset_days: int = 0,
) -> ExternalTradePlanSnapshot:
    window = _window()
    return ExternalTradePlanSnapshot(
        session=session or window.session,
        session_open_at=window.opens_at_utc + timedelta(days=session_open_offset_days),
        observed_through=window.opens_at_utc + timedelta(minutes=observed_offset_minutes),
        available_at=window.opens_at_utc + timedelta(minutes=available_offset_minutes),
        side=side,
        entry_price=entry_price,
        structural_invalidation_price=stop_price,
        target_price=target_price,
        source="trader_annotation",
        source_version="v1",
    )


def test_buy_exactly_2r_is_accepted_with_full_target_exit() -> None:
    window = _window()
    plan = bind_trade_plan(
        _snapshot(),
        window=window,
        decision_at=window.opens_at_utc + timedelta(minutes=41),
    )

    assert plan.status is TradePlanStatus.ACCEPTED
    assert plan.risk_reward.ratio == 2.0
    assert plan.exit_management is ExitManagement.FULL_AT_TARGET
    assert plan.first_2r_price == 110.0
    assert plan.remainder_rule_resolved is True
    assert plan.source == "trader_annotation@v1"


def test_sell_exactly_2r_is_accepted() -> None:
    window = _window()
    plan = bind_trade_plan(
        _snapshot(
            side=TradeSide.SELL,
            entry_price=100.0,
            stop_price=105.0,
            target_price=90.0,
        ),
        window=window,
        decision_at=window.opens_at_utc + timedelta(minutes=41),
    )

    assert plan.status is TradePlanStatus.ACCEPTED
    assert plan.risk_reward.ratio == 2.0
    assert plan.exit_management is ExitManagement.FULL_AT_TARGET


def test_below_2r_is_rejected_instead_of_moving_stop() -> None:
    window = _window()
    plan = bind_trade_plan(
        _snapshot(target_price=107.5),
        window=window,
        decision_at=window.opens_at_utc + timedelta(minutes=41),
    )

    assert plan.status is TradePlanStatus.REJECTED
    assert plan.risk_reward.ratio == 1.5
    assert plan.exit_management is ExitManagement.NOT_APPLICABLE
    assert plan.first_2r_price is None
    assert "below" in plan.reason


def test_greater_than_2r_records_partial_at_2r_and_unresolved_remainder() -> None:
    window = _window()
    plan = bind_trade_plan(
        _snapshot(target_price=115.0),
        window=window,
        decision_at=window.opens_at_utc + timedelta(minutes=41),
    )

    assert plan.status is TradePlanStatus.ACCEPTED
    assert plan.risk_reward.ratio == 3.0
    assert plan.exit_management is ExitManagement.PARTIAL_AT_2R_REMAINDER_UNRESOLVED
    assert plan.first_2r_price == 110.0
    assert plan.remainder_rule_resolved is False
    assert "unresolved" in plan.reason


def test_sell_greater_than_2r_computes_2r_price_below_entry() -> None:
    window = _window()
    plan = bind_trade_plan(
        _snapshot(
            side=TradeSide.SELL,
            entry_price=100.0,
            stop_price=104.0,
            target_price=86.0,
        ),
        window=window,
        decision_at=window.opens_at_utc + timedelta(minutes=41),
    )

    assert plan.risk_reward.ratio == 3.5
    assert plan.first_2r_price == 92.0


def test_invalid_buy_geometry_is_rejected_as_data_error() -> None:
    with pytest.raises(TradePlanDataError, match="stop < entry < target"):
        _snapshot(entry_price=100.0, stop_price=101.0, target_price=110.0)


def test_invalid_sell_geometry_is_rejected_as_data_error() -> None:
    with pytest.raises(TradePlanDataError, match="target < entry < stop"):
        _snapshot(
            side=TradeSide.SELL,
            entry_price=100.0,
            stop_price=95.0,
            target_price=90.0,
        )


def test_plan_cannot_be_available_before_latest_observation() -> None:
    with pytest.raises(TradePlanDataError, match="latest observation"):
        _snapshot(observed_offset_minutes=42, available_offset_minutes=41)


def test_future_trade_plan_is_rejected_at_decision_time() -> None:
    window = _window()
    snapshot = _snapshot(observed_offset_minutes=45, available_offset_minutes=45)

    with pytest.raises(TradePlanDataError, match="after decision time"):
        bind_trade_plan(
            snapshot,
            window=window,
            decision_at=window.opens_at_utc + timedelta(minutes=41),
        )


def test_trade_plan_cannot_authorize_before_or_completion() -> None:
    window = _window()
    snapshot = _snapshot(observed_offset_minutes=30, available_offset_minutes=30)

    with pytest.raises(TradePlanDataError, match="before the Opening Range is complete"):
        bind_trade_plan(
            snapshot,
            window=window,
            decision_at=window.opens_at_utc + timedelta(minutes=30),
        )


def test_mismatched_session_is_rejected() -> None:
    window = _window()
    snapshot = _snapshot(session=SessionKind.EUROPE_LONDON)

    with pytest.raises(TradePlanDataError, match="different session"):
        bind_trade_plan(
            snapshot,
            window=window,
            decision_at=window.opens_at_utc + timedelta(minutes=41),
        )


def test_mismatched_session_open_is_rejected() -> None:
    window = _window()
    snapshot = _snapshot(session_open_offset_days=-1)

    with pytest.raises(TradePlanDataError, match="opening does not match"):
        bind_trade_plan(
            snapshot,
            window=window,
            decision_at=window.opens_at_utc + timedelta(minutes=41),
        )
