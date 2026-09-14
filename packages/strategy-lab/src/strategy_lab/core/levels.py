"""External A/C level contract for ACD v0.1.

The exact A/C formulas are intentionally unknown in v0.1. The strategy layer
therefore accepts timestamped levels from a named external indicator/provider
and binds them to the Opening Range reconstructed independently from candles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Protocol

from .models import AcdLevels, SessionKind
from .opening_range import OpeningRange
from .sessions import SessionWindow


class AcdLevelDataError(ValueError):
    """Raised when supplied ACD levels violate the v0.1 research contract."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AcdLevelDataError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ExternalAcdLevelSnapshot:
    """A/C values supplied by an external indicator for one session.

    `available_at` records when this exact snapshot was available to the
    strategy. It is part of the anti-lookahead contract.
    """

    session: SessionKind
    session_open_at: datetime
    available_at: datetime
    a_up: float
    c_up: float
    a_down: float
    c_down: float
    source: str
    source_version: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.session_open_at, field_name="session_open_at")
        _require_aware(self.available_at, field_name="available_at")

        values = (self.a_up, self.c_up, self.a_down, self.c_down)
        if not all(isfinite(value) for value in values):
            raise AcdLevelDataError("external A/C values must be finite")
        if self.c_up <= self.a_up:
            raise AcdLevelDataError("C_UP must be above A_UP")
        if self.a_down <= self.c_down:
            raise AcdLevelDataError("A_DOWN must be above C_DOWN")
        if not self.source.strip():
            raise AcdLevelDataError("external ACD level source must be recorded")
        if self.source_version is not None and not self.source_version.strip():
            raise AcdLevelDataError("source_version cannot be blank when supplied")

    @property
    def source_identity(self) -> str:
        if self.source_version is None:
            return self.source
        return f"{self.source}@{self.source_version}"


class AcdLevelProvider(Protocol):
    """Interface for retrieving a frozen external level snapshot."""

    def get_snapshot(
        self,
        *,
        session: SessionKind,
        session_open_at: datetime,
    ) -> ExternalAcdLevelSnapshot:
        """Return the externally supplied A/C levels for one session."""
        ...


def bind_external_acd_levels(
    snapshot: ExternalAcdLevelSnapshot,
    *,
    window: SessionWindow,
    opening_range: OpeningRange,
    decision_at: datetime,
) -> AcdLevels:
    """Bind external A/C values to the independently reconstructed OR.

    This function enforces session identity and timestamp causality. It does
    not calculate or infer any missing A/C formula.
    """

    _require_aware(decision_at, field_name="decision_at")

    decision_utc = decision_at.astimezone(UTC)
    snapshot_open_utc = snapshot.session_open_at.astimezone(UTC)
    snapshot_available_utc = snapshot.available_at.astimezone(UTC)

    if snapshot.session != window.session:
        raise AcdLevelDataError("external ACD snapshot belongs to a different session")
    if snapshot_open_utc != window.opens_at_utc:
        raise AcdLevelDataError("external ACD snapshot session opening does not match window")
    if opening_range.starts_at_utc != window.opens_at_utc:
        raise AcdLevelDataError("Opening Range start does not match session window")
    if opening_range.ends_at_utc != window.opening_range_ends_at_utc:
        raise AcdLevelDataError("Opening Range end does not match session window")
    if decision_utc < window.opening_range_ends_at_utc:
        raise AcdLevelDataError("ACD levels cannot be used before the Opening Range is complete")
    if snapshot_available_utc < window.opening_range_ends_at_utc:
        raise AcdLevelDataError("external ACD snapshot claims availability before OR completion")
    if snapshot_available_utc > decision_utc:
        raise AcdLevelDataError("external ACD snapshot was not available at decision time")

    try:
        return AcdLevels(
            c_up=snapshot.c_up,
            a_up=snapshot.a_up,
            or_up=opening_range.high,
            or_down=opening_range.low,
            a_down=snapshot.a_down,
            c_down=snapshot.c_down,
            source=snapshot.source_identity,
        )
    except ValueError as exc:
        raise AcdLevelDataError(str(exc)) from exc
