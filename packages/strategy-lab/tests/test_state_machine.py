from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_lab.core.models import MomentumClass, SessionKind, TrendDirection
from strategy_lab.core.sessions import build_session_window
from strategy_lab.core.state_machine import (
    AcdBoundary,
    AcdDecisionLedger,
    ConfirmationMode,
    ConfirmationResult,
    SetupSnapshot,
    SetupState,
    SetupStateError,
)
from strategy_lab.core.trade_plan import (
    ExternalTradePlanSnapshot,
    TradeSide,
    ValidatedTradePlan,
    bind_trade_plan,
)

SESSION_OPEN = datetime(2026, 9, 14, 13, 30, tzinfo=UTC)


def _start() -> AcdDecisionLedger:
    return AcdDecisionLedger.start(
        instrument="XAUUSD",
        session=SessionKind.AMERICA_NEW_YORK,
        session_open_at=SESSION_OPEN,
        started_at=SESSION_OPEN - timedelta(minutes=1),
    )


def _accepted_trade_plan() -> ValidatedTradePlan:
    window = build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="UTC",
    )
    available_at = SESSION_OPEN + timedelta(minutes=42)
    snapshot = ExternalTradePlanSnapshot(
        session=SessionKind.AMERICA_NEW_YORK,
        session_open_at=SESSION_OPEN,
        observed_through=available_at,
        available_at=available_at,
        side=TradeSide.BUY,
        entry_price=100.0,
        structural_invalidation_price=95.0,
        target_price=110.0,
        source="trader_annotation",
        source_version="v1",
    )
    return bind_trade_plan(snapshot, window=window, decision_at=available_at)


def _to_boundary() -> AcdDecisionLedger:
    ledger = _start()
    ledger = ledger.transition(SetupSnapshot(at=SESSION_OPEN, state=SetupState.OR_FORMING))
    ledger = ledger.transition(
        SetupSnapshot(at=SESSION_OPEN + timedelta(minutes=40), state=SetupState.OR_READY)
    )
    ledger = ledger.transition(
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=40),
            state=SetupState.WAITING_FOR_BOUNDARY,
        )
    )
    return ledger.transition(
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=41),
            state=SetupState.BOUNDARY_TOUCHED,
            previous_trend=TrendDirection.BULLISH,
            m15_direction=TrendDirection.BULLISH,
            m5_direction=TrendDirection.BULLISH,
            boundary=AcdBoundary.A_DOWN,
        )
    )


def _candidate() -> AcdDecisionLedger:
    waiting = _to_boundary().transition(
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=41),
            state=SetupState.WAITING_FOR_CONFIRMATION,
            previous_trend=TrendDirection.BULLISH,
            m15_direction=TrendDirection.BULLISH,
            m5_direction=TrendDirection.BULLISH,
            boundary=AcdBoundary.A_DOWN,
            momentum=MomentumClass.NORMAL_OR_WEAK,
            confirmation_mode=ConfirmationMode.ONE_CANDLE,
        )
    )
    return waiting.transition(
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=42),
            state=SetupState.CANDIDATE_READY,
            previous_trend=TrendDirection.BULLISH,
            m15_direction=TrendDirection.BULLISH,
            m5_direction=TrendDirection.BULLISH,
            boundary=AcdBoundary.A_DOWN,
            momentum=MomentumClass.NORMAL_OR_WEAK,
            confirmation_mode=ConfirmationMode.ONE_CANDLE,
            confirmation_result=ConfirmationResult.CONFIRMED,
        )
    )


def test_full_setup_path_is_auditable_and_immutable() -> None:
    boundary_ledger = _to_boundary()
    candidate = _candidate()
    trade_plan = _accepted_trade_plan()
    accepted = candidate.transition(
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=42),
            state=SetupState.ACCEPTED,
            previous_trend=TrendDirection.BULLISH,
            m15_direction=TrendDirection.BULLISH,
            m5_direction=TrendDirection.BULLISH,
            boundary=AcdBoundary.A_DOWN,
            momentum=MomentumClass.NORMAL_OR_WEAK,
            confirmation_mode=ConfirmationMode.ONE_CANDLE,
            confirmation_result=ConfirmationResult.CONFIRMED,
            trade_plan=trade_plan,
            reason="confirmed setup has a causally valid trade plan at 1:2",
        )
    )

    assert boundary_ledger.current_state is SetupState.BOUNDARY_TOUCHED
    assert accepted.current_state is SetupState.ACCEPTED
    assert accepted.is_terminal is True
    assert len(boundary_ledger.entries) == 5
    assert len(accepted.entries) == 8


def test_accepted_setup_requires_validated_trade_plan() -> None:
    with pytest.raises(SetupStateError, match="requires a validated trade plan"):
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=42),
            state=SetupState.ACCEPTED,
            previous_trend=TrendDirection.BULLISH,
            m15_direction=TrendDirection.BULLISH,
            m5_direction=TrendDirection.BULLISH,
            boundary=AcdBoundary.A_DOWN,
            momentum=MomentumClass.NORMAL_OR_WEAK,
            confirmation_mode=ConfirmationMode.ONE_CANDLE,
            confirmation_result=ConfirmationResult.CONFIRMED,
            reason="missing plan should fail",
        )


def test_trade_plan_values_cannot_conflict_with_snapshot() -> None:
    with pytest.raises(SetupStateError, match="entry_price conflicts"):
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=42),
            state=SetupState.ACCEPTED,
            previous_trend=TrendDirection.BULLISH,
            m15_direction=TrendDirection.BULLISH,
            m5_direction=TrendDirection.BULLISH,
            boundary=AcdBoundary.A_DOWN,
            momentum=MomentumClass.NORMAL_OR_WEAK,
            confirmation_mode=ConfirmationMode.ONE_CANDLE,
            confirmation_result=ConfirmationResult.CONFIRMED,
            entry_price=101.0,
            trade_plan=_accepted_trade_plan(),
            reason="conflicting duplicate data should fail",
        )


def test_invalid_transition_is_rejected() -> None:
    ledger = _start()

    with pytest.raises(SetupStateError, match="invalid setup transition"):
        ledger.transition(
            SetupSnapshot(at=SESSION_OPEN, state=SetupState.WAITING_FOR_BOUNDARY)
        )


def test_backward_timestamp_is_rejected() -> None:
    ledger = _start().transition(
        SetupSnapshot(at=SESSION_OPEN + timedelta(minutes=1), state=SetupState.OR_FORMING)
    )

    with pytest.raises(SetupStateError, match="timestamps must be non-decreasing"):
        ledger.transition(
            SetupSnapshot(
                at=SESSION_OPEN + timedelta(seconds=30),
                state=SetupState.OR_READY,
            )
        )


def test_terminal_state_cannot_transition() -> None:
    ledger = _to_boundary().transition(
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=41),
            state=SetupState.UNRESOLVED,
            boundary=AcdBoundary.A_DOWN,
            reason="momentum threshold is not yet canonical",
        )
    )

    with pytest.raises(SetupStateError, match="invalid setup transition"):
        ledger.transition(
            SetupSnapshot(
                at=SESSION_OPEN + timedelta(minutes=42),
                state=SetupState.WAITING_FOR_CONFIRMATION,
                boundary=AcdBoundary.A_DOWN,
            )
        )


def test_terminal_state_requires_reason() -> None:
    with pytest.raises(SetupStateError, match="explicit reason"):
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=41),
            state=SetupState.REJECTED,
            boundary=AcdBoundary.C_UP,
        )


def test_candidate_ready_requires_resolved_momentum_and_confirmation() -> None:
    with pytest.raises(SetupStateError, match="momentum is unresolved"):
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=42),
            state=SetupState.CANDIDATE_READY,
            boundary=AcdBoundary.A_DOWN,
            confirmation_mode=ConfirmationMode.ONE_CANDLE,
            confirmation_result=ConfirmationResult.CONFIRMED,
        )


def test_accepted_serialization_uses_trade_plan_values() -> None:
    accepted = _candidate().transition(
        SetupSnapshot(
            at=SESSION_OPEN + timedelta(minutes=42),
            state=SetupState.ACCEPTED,
            previous_trend=TrendDirection.BULLISH,
            m15_direction=TrendDirection.BULLISH,
            m5_direction=TrendDirection.BULLISH,
            boundary=AcdBoundary.A_DOWN,
            momentum=MomentumClass.NORMAL_OR_WEAK,
            confirmation_mode=ConfirmationMode.ONE_CANDLE,
            confirmation_result=ConfirmationResult.CONFIRMED,
            trade_plan=_accepted_trade_plan(),
            reason="valid plan",
        )
    )
    payload = accepted.to_dict()
    entries = payload["entries"]
    assert isinstance(entries, list)
    terminal = entries[-1]
    assert terminal["entry_price"] == 100.0
    assert terminal["stop_price"] == 95.0
    assert terminal["target_price"] == 110.0
    assert terminal["risk_reward"]["ratio"] == 2.0
    assert terminal["trade_plan"]["source"] == "trader_annotation@v1"


def test_serialization_is_versioned_and_uses_utc() -> None:
    payload = _to_boundary().to_dict()

    assert payload["schema_version"] == "acd-decision-ledger-v0.1"
    assert payload["strategy_version"] == "acd-fast-scalp-v0.1"
    assert payload["instrument"] == "XAUUSD"
    assert payload["session"] == "america_new_york"
    assert payload["session_open_at"] == "2026-09-14T13:30:00+00:00"

    entries = payload["entries"]
    assert isinstance(entries, list)
    assert entries[-1]["state"] == "boundary_touched"
