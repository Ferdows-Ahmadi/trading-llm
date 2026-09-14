"""Auditable ACD v0.1 setup state machine and append-only decision ledger.

This module models *what state the strategy was in at a given instant*. It does
not invent unresolved momentum, candle-confirmation, stop, or target formulas.
Each transition is immutable, timestamped, source-independent, and ordered so a
later candle cannot rewrite an earlier decision record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite

from .models import DecisionStatus, MomentumClass, RiskReward, SessionKind, TrendDirection

LEDGER_SCHEMA_VERSION = "acd-decision-ledger-v0.1"
STRATEGY_VERSION = "acd-fast-scalp-v0.1"


class SetupState(StrEnum):
    SESSION_WAIT = "session_wait"
    OR_FORMING = "or_forming"
    OR_READY = "or_ready"
    WAITING_FOR_BOUNDARY = "waiting_for_boundary"
    BOUNDARY_TOUCHED = "boundary_touched"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    CANDIDATE_READY = "candidate_ready"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class AcdBoundary(StrEnum):
    A_UP = "a_up"
    C_UP = "c_up"
    A_DOWN = "a_down"
    C_DOWN = "c_down"


class ConfirmationMode(StrEnum):
    ONE_CANDLE = "one_candle"
    THREE_CANDLE = "three_candle"
    UNRESOLVED = "unresolved"


class ConfirmationResult(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNRESOLVED = "unresolved"


_TERMINAL_STATES = frozenset(
    {SetupState.ACCEPTED, SetupState.REJECTED, SetupState.UNRESOLVED}
)

_ALLOWED_TRANSITIONS: dict[SetupState, frozenset[SetupState]] = {
    SetupState.SESSION_WAIT: frozenset({SetupState.OR_FORMING}),
    SetupState.OR_FORMING: frozenset({SetupState.OR_READY}),
    SetupState.OR_READY: frozenset({SetupState.WAITING_FOR_BOUNDARY}),
    SetupState.WAITING_FOR_BOUNDARY: frozenset({SetupState.BOUNDARY_TOUCHED}),
    SetupState.BOUNDARY_TOUCHED: frozenset(
        {
            SetupState.WAITING_FOR_CONFIRMATION,
            SetupState.REJECTED,
            SetupState.UNRESOLVED,
        }
    ),
    SetupState.WAITING_FOR_CONFIRMATION: frozenset(
        {
            SetupState.CANDIDATE_READY,
            SetupState.REJECTED,
            SetupState.UNRESOLVED,
        }
    ),
    SetupState.CANDIDATE_READY: frozenset(
        {SetupState.ACCEPTED, SetupState.REJECTED, SetupState.UNRESOLVED}
    ),
    SetupState.ACCEPTED: frozenset(),
    SetupState.REJECTED: frozenset(),
    SetupState.UNRESOLVED: frozenset(),
}


class SetupStateError(ValueError):
    """Raised when a setup transition or ledger record is invalid."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SetupStateError(f"{field_name} must be timezone-aware")


def _finite_optional(value: float | None, *, field_name: str) -> None:
    if value is not None and not isfinite(value):
        raise SetupStateError(f"{field_name} must be finite when supplied")


@dataclass(frozen=True, slots=True)
class SetupSnapshot:
    """One immutable strategy-state transition at one known instant."""

    at: datetime
    state: SetupState
    previous_trend: TrendDirection = TrendDirection.UNRESOLVED
    m15_direction: TrendDirection = TrendDirection.UNRESOLVED
    m5_direction: TrendDirection = TrendDirection.UNRESOLVED
    boundary: AcdBoundary | None = None
    momentum: MomentumClass = MomentumClass.UNRESOLVED
    confirmation_mode: ConfirmationMode = ConfirmationMode.UNRESOLVED
    confirmation_result: ConfirmationResult = ConfirmationResult.NOT_EVALUATED
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    risk_reward: RiskReward | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        _require_aware(self.at, field_name="at")
        _finite_optional(self.entry_price, field_name="entry_price")
        _finite_optional(self.stop_price, field_name="stop_price")
        _finite_optional(self.target_price, field_name="target_price")

        boundary_required_states = {
            SetupState.BOUNDARY_TOUCHED,
            SetupState.WAITING_FOR_CONFIRMATION,
            SetupState.CANDIDATE_READY,
            SetupState.ACCEPTED,
            SetupState.REJECTED,
            SetupState.UNRESOLVED,
        }
        if self.state in boundary_required_states and self.boundary is None:
            raise SetupStateError(f"boundary is required in state {self.state.value}")

        if self.state in {SetupState.CANDIDATE_READY, SetupState.ACCEPTED}:
            if self.momentum is MomentumClass.UNRESOLVED:
                raise SetupStateError("candidate cannot be ready while momentum is unresolved")
            if self.confirmation_mode is ConfirmationMode.UNRESOLVED:
                raise SetupStateError("candidate cannot be ready while confirmation mode is unresolved")
            if self.confirmation_result is not ConfirmationResult.CONFIRMED:
                raise SetupStateError("candidate-ready/accepted state requires confirmed execution")

        if self.state in _TERMINAL_STATES and not self.reason.strip():
            raise SetupStateError("terminal setup state requires an explicit reason")

    @property
    def decision_status(self) -> DecisionStatus | None:
        if self.state is SetupState.ACCEPTED:
            return DecisionStatus.ACCEPTED
        if self.state is SetupState.REJECTED:
            return DecisionStatus.REJECTED
        if self.state is SetupState.UNRESOLVED:
            return DecisionStatus.UNRESOLVED
        return None

    def to_dict(self) -> dict[str, object]:
        rr_payload: dict[str, float] | None = None
        if self.risk_reward is not None:
            rr_payload = {
                "risk": self.risk_reward.risk,
                "reward": self.risk_reward.reward,
                "ratio": self.risk_reward.ratio,
            }

        return {
            "at": self.at.astimezone(UTC).isoformat(),
            "state": self.state.value,
            "previous_trend": self.previous_trend.value,
            "m15_direction": self.m15_direction.value,
            "m5_direction": self.m5_direction.value,
            "boundary": self.boundary.value if self.boundary is not None else None,
            "momentum": self.momentum.value,
            "confirmation_mode": self.confirmation_mode.value,
            "confirmation_result": self.confirmation_result.value,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "risk_reward": rr_payload,
            "decision_status": (
                self.decision_status.value if self.decision_status is not None else None
            ),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AcdDecisionLedger:
    """Immutable ordered transition history for one instrument/session setup."""

    instrument: str
    session: SessionKind
    session_open_at: datetime
    entries: tuple[SetupSnapshot, ...]
    strategy_version: str = STRATEGY_VERSION
    schema_version: str = LEDGER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_aware(self.session_open_at, field_name="session_open_at")
        if not self.instrument.strip():
            raise SetupStateError("instrument must be recorded")
        if not self.strategy_version.strip():
            raise SetupStateError("strategy_version must be recorded")
        if not self.schema_version.strip():
            raise SetupStateError("schema_version must be recorded")
        if not self.entries:
            raise SetupStateError("decision ledger must contain at least one entry")
        if self.entries[0].state is not SetupState.SESSION_WAIT:
            raise SetupStateError("decision ledger must start in SESSION_WAIT")

        session_open_utc = self.session_open_at.astimezone(UTC)
        previous: SetupSnapshot | None = None
        for entry in self.entries:
            if entry.at.astimezone(UTC) < session_open_utc and entry.state is not SetupState.SESSION_WAIT:
                raise SetupStateError("post-session states cannot precede the session opening")
            if previous is not None:
                if entry.at.astimezone(UTC) < previous.at.astimezone(UTC):
                    raise SetupStateError("decision ledger timestamps must be non-decreasing")
                if entry.state not in _ALLOWED_TRANSITIONS[previous.state]:
                    raise SetupStateError(
                        f"invalid setup transition: {previous.state.value} -> {entry.state.value}"
                    )
            previous = entry

    @classmethod
    def start(
        cls,
        *,
        instrument: str,
        session: SessionKind,
        session_open_at: datetime,
        started_at: datetime,
        strategy_version: str = STRATEGY_VERSION,
    ) -> AcdDecisionLedger:
        """Create a new ledger in SESSION_WAIT."""
        return cls(
            instrument=instrument,
            session=session,
            session_open_at=session_open_at,
            strategy_version=strategy_version,
            entries=(SetupSnapshot(at=started_at, state=SetupState.SESSION_WAIT),),
        )

    def transition(self, snapshot: SetupSnapshot) -> AcdDecisionLedger:
        """Return a new ledger with one validated transition appended."""
        return AcdDecisionLedger(
            instrument=self.instrument,
            session=self.session,
            session_open_at=self.session_open_at,
            strategy_version=self.strategy_version,
            schema_version=self.schema_version,
            entries=(*self.entries, snapshot),
        )

    @property
    def current_state(self) -> SetupState:
        return self.entries[-1].state

    @property
    def is_terminal(self) -> bool:
        return self.current_state in _TERMINAL_STATES

    def to_dict(self) -> dict[str, object]:
        """Serialize with an explicit schema version for durable replay artifacts."""
        return {
            "schema_version": self.schema_version,
            "strategy_version": self.strategy_version,
            "instrument": self.instrument,
            "session": self.session.value,
            "session_open_at": self.session_open_at.astimezone(UTC).isoformat(),
            "entries": [entry.to_dict() for entry in self.entries],
        }
