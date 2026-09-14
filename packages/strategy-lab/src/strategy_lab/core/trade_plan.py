"""Structural stop, target, and risk/reward contract for ACD Fast Scalp v0.1.

The strategy source defines the *meaning* of the stop and minimum R:R but does
not yet define algorithms that select the main structural swing or target.
This module therefore consumes timestamped provider/annotation values, validates
causality and geometry, and applies the deterministic 1:2 gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isclose, isfinite
from typing import Protocol

from .models import RiskReward, SessionKind
from .sessions import SessionWindow

MINIMUM_RR = 2.0


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class TradePlanStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ExitManagement(StrEnum):
    FULL_AT_TARGET = "full_at_target"
    PARTIAL_AT_2R_REMAINDER_UNRESOLVED = "partial_at_2r_remainder_unresolved"
    NOT_APPLICABLE = "not_applicable"


class TradePlanDataError(ValueError):
    """Raised when a supplied structural trade plan is malformed or non-causal."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TradePlanDataError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ExternalTradePlanSnapshot:
    """Provider/annotation supplied entry, structural invalidation, and target."""

    session: SessionKind
    session_open_at: datetime
    observed_through: datetime
    available_at: datetime
    side: TradeSide
    entry_price: float
    structural_invalidation_price: float
    target_price: float
    source: str
    source_version: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in {
            "session_open_at": self.session_open_at,
            "observed_through": self.observed_through,
            "available_at": self.available_at,
        }.items():
            _require_aware(value, field_name=field_name)

        prices = (
            self.entry_price,
            self.structural_invalidation_price,
            self.target_price,
        )
        if not all(isfinite(value) for value in prices):
            raise TradePlanDataError("trade-plan prices must be finite")
        if any(value <= 0 for value in prices):
            raise TradePlanDataError("trade-plan prices must be greater than zero")

        observed_utc = self.observed_through.astimezone(UTC)
        available_utc = self.available_at.astimezone(UTC)
        if available_utc < observed_utc:
            raise TradePlanDataError(
                "trade plan cannot be available before its latest observation"
            )

        if self.side is TradeSide.BUY:
            if not (
                self.structural_invalidation_price
                < self.entry_price
                < self.target_price
            ):
                raise TradePlanDataError(
                    "BUY trade plan must satisfy stop < entry < target"
                )
        else:
            if not (
                self.target_price
                < self.entry_price
                < self.structural_invalidation_price
            ):
                raise TradePlanDataError(
                    "SELL trade plan must satisfy target < entry < stop"
                )

        if not self.source.strip():
            raise TradePlanDataError("trade-plan source must be recorded")
        if self.source_version is not None and not self.source_version.strip():
            raise TradePlanDataError("source_version cannot be blank when supplied")

    @property
    def source_identity(self) -> str:
        if self.source_version is None:
            return self.source
        return f"{self.source}@{self.source_version}"


class TradePlanProvider(Protocol):
    """Interface for retrieving a structural trade plan known at decision time."""

    def get_snapshot(
        self,
        *,
        session: SessionKind,
        session_open_at: datetime,
        decision_at: datetime,
    ) -> ExternalTradePlanSnapshot:
        """Return a sourced plan available no later than `decision_at`."""
        ...


@dataclass(frozen=True, slots=True)
class ValidatedTradePlan:
    """Causally validated ACD trade plan with deterministic R:R disposition."""

    session: SessionKind
    side: TradeSide
    entry_price: float
    structural_invalidation_price: float
    target_price: float
    risk_reward: RiskReward
    status: TradePlanStatus
    exit_management: ExitManagement
    first_2r_price: float | None
    remainder_rule_resolved: bool
    source: str
    observed_through_utc: datetime
    available_at_utc: datetime
    reason: str

    @property
    def meets_minimum_rr(self) -> bool:
        return self.risk_reward.meets_acd_v01_minimum


def bind_trade_plan(
    snapshot: ExternalTradePlanSnapshot,
    *,
    window: SessionWindow,
    decision_at: datetime,
) -> ValidatedTradePlan:
    """Bind a provider-supplied structural plan and apply the frozen 1:2 rule."""

    _require_aware(decision_at, field_name="decision_at")

    decision_utc = decision_at.astimezone(UTC)
    snapshot_open_utc = snapshot.session_open_at.astimezone(UTC)
    observed_utc = snapshot.observed_through.astimezone(UTC)
    available_utc = snapshot.available_at.astimezone(UTC)

    if snapshot.session != window.session:
        raise TradePlanDataError("trade plan belongs to a different session")
    if snapshot_open_utc != window.opens_at_utc:
        raise TradePlanDataError("trade-plan session opening does not match session window")
    if decision_utc < window.opening_range_ends_at_utc:
        raise TradePlanDataError(
            "trade plan cannot authorize an ACD trade before the Opening Range is complete"
        )
    if observed_utc > decision_utc:
        raise TradePlanDataError("trade plan contains observations from after decision time")
    if available_utc > decision_utc:
        raise TradePlanDataError("trade plan was not available at decision time")

    if snapshot.side is TradeSide.BUY:
        risk = snapshot.entry_price - snapshot.structural_invalidation_price
        reward = snapshot.target_price - snapshot.entry_price
        two_r_price = snapshot.entry_price + (MINIMUM_RR * risk)
    else:
        risk = snapshot.structural_invalidation_price - snapshot.entry_price
        reward = snapshot.entry_price - snapshot.target_price
        two_r_price = snapshot.entry_price - (MINIMUM_RR * risk)

    risk_reward = RiskReward(risk=risk, reward=reward)
    ratio = risk_reward.ratio

    if ratio < MINIMUM_RR and not isclose(ratio, MINIMUM_RR, rel_tol=1e-12, abs_tol=1e-12):
        return ValidatedTradePlan(
            session=snapshot.session,
            side=snapshot.side,
            entry_price=snapshot.entry_price,
            structural_invalidation_price=snapshot.structural_invalidation_price,
            target_price=snapshot.target_price,
            risk_reward=risk_reward,
            status=TradePlanStatus.REJECTED,
            exit_management=ExitManagement.NOT_APPLICABLE,
            first_2r_price=None,
            remainder_rule_resolved=False,
            source=snapshot.source_identity,
            observed_through_utc=observed_utc,
            available_at_utc=available_utc,
            reason="risk/reward is below the ACD v0.1 minimum of 1:2",
        )

    if isclose(ratio, MINIMUM_RR, rel_tol=1e-12, abs_tol=1e-12):
        management = ExitManagement.FULL_AT_TARGET
        first_2r_price: float | None = snapshot.target_price
        remainder_resolved = True
        reason = "risk/reward is 1:2; close the full position at target"
    else:
        management = ExitManagement.PARTIAL_AT_2R_REMAINDER_UNRESOLVED
        first_2r_price = two_r_price
        remainder_resolved = False
        reason = (
            "risk/reward exceeds 1:2; take a partial exit at 2R; "
            "partial percentage and remainder exit rule are unresolved"
        )

    return ValidatedTradePlan(
        session=snapshot.session,
        side=snapshot.side,
        entry_price=snapshot.entry_price,
        structural_invalidation_price=snapshot.structural_invalidation_price,
        target_price=snapshot.target_price,
        risk_reward=risk_reward,
        status=TradePlanStatus.ACCEPTED,
        exit_management=management,
        first_2r_price=first_2r_price,
        remainder_rule_resolved=remainder_resolved,
        source=snapshot.source_identity,
        observed_through_utc=observed_utc,
        available_at_utc=available_utc,
        reason=reason,
    )
