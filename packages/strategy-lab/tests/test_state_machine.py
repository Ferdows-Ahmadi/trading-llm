from datetime import UTC, datetime, timedelta

import pytest

from strategy_lab.core.models import MomentumClass, SessionKind, TrendDirection
from strategy_lab.core.state_machine import (
    AcdBoundary,
    AcdDecisionLedger,
    ConfirmationMode,
    ConfirmationResult,
    SetupSnapshot,
    SetupState,
    SetupStateError,
)

SESSION_OPEN = datetime(2026, 9, 14, 13, 30, tzinfo=UTC)


def _start() -> AcdDecisionLedger:
    return AcdDecisionLedger.start(
        instrument="XAUUSD",
        session=SessionKind.AMERICA_NEW_YORK,
        session_open_at=SESSION_OPEN,
        started_at=SESSION_OPEN - timedelta(minutes=1),
    )


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


def test_full_setup_path_is_auditable_and_immutable() -> None:
    boundary_ledger = _to_boundary()
    waiting = boundary_ledger.transition(
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
    candidate = waiting.transition(
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
            reason="all currently formalized setup gates passed",
        )
    )

    assert boundary_ledger.current_state is SetupState.BOUNDARY_TOUCHED
    assert accepted.current_state is SetupState.ACCEPTED
    assert accepted.is_terminal is True
    assert len(boundary_ledger.entries) == 5
    assert len(accepted.entries) == 8


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
