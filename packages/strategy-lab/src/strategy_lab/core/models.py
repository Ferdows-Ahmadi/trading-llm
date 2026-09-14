"""Shared domain types for strategy research.

These types intentionally distinguish known strategy states from unresolved ones.
The project must not coerce missing human definitions into fabricated numeric rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SessionKind(StrEnum):
    """Canonical regional session identities used by ACD v0.1."""

    ASIA_SINGAPORE = "asia_singapore"
    EUROPE_LONDON = "europe_london"
    AMERICA_NEW_YORK = "america_new_york"


class TrendDirection(StrEnum):
    """Directional structure state used by the strategy contract."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    UNCLEAR = "unclear"
    UNRESOLVED = "unresolved"


class MomentumClass(StrEnum):
    """Qualitative approach-momentum state.

    No numeric threshold is authorized in ACD v0.1, so callers may provide a
    sourced classification or leave the state unresolved.
    """

    NORMAL_OR_WEAK = "normal_or_weak"
    STRONG_OPPOSING = "strong_opposing"
    UNRESOLVED = "unresolved"


class DecisionStatus(StrEnum):
    """Terminal or non-terminal research decision state."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class AcdLevels:
    """Externally supplied ACD levels for one session.

    A/C formulas are not known in v0.1. This object validates ordering only;
    it does not calculate levels.
    """

    c_up: float
    a_up: float
    or_up: float
    or_down: float
    a_down: float
    c_down: float
    source: str

    def __post_init__(self) -> None:
        ordered = (
            self.c_up,
            self.a_up,
            self.or_up,
            self.or_down,
            self.a_down,
            self.c_down,
        )
        if not all(left > right for left, right in zip(ordered, ordered[1:], strict=True)):
            raise ValueError(
                "ACD levels must satisfy C_UP > A_UP > OR_UP > OR_DOWN > A_DOWN > C_DOWN"
            )
        if not self.source.strip():
            raise ValueError("ACD level source must be recorded")


@dataclass(frozen=True, slots=True)
class RiskReward:
    """Simple deterministic risk/reward calculation for a candidate trade."""

    risk: float
    reward: float

    def __post_init__(self) -> None:
        if self.risk <= 0:
            raise ValueError("risk must be greater than zero")
        if self.reward <= 0:
            raise ValueError("reward must be greater than zero")

    @property
    def ratio(self) -> float:
        return self.reward / self.risk

    @property
    def meets_acd_v01_minimum(self) -> bool:
        return self.ratio >= 2.0
