"""Directional-context contract for ACD v0.1.

Previous trend and M15/M5 direction are known strategy concepts, but their
fully deterministic chart-reading algorithms are not frozen yet. This module
therefore accepts timestamped labels from a named provider/annotation source
and enforces session identity plus anti-lookahead rules.

M1 is intentionally absent from this context contract. In ACD v0.1 M1 is an
execution timeframe and must not independently set directional bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from .models import SessionKind, TrendDirection
from .sessions import SessionWindow


class DirectionalContextDataError(ValueError):
    """Raised when directional context violates the v0.1 research contract."""


def _require_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DirectionalContextDataError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ExternalDirectionalContextSnapshot:
    """Timestamped previous-trend and M15/M5 labels for one ACD session.

    `previous_trend_observed_through` must not extend into the current Opening
    Range. M15 and M5 labels may evolve after the OR, but every observation and
    the completed snapshot must be available no later than the decision time
    at which the context is consumed.
    """

    session: SessionKind
    session_open_at: datetime
    available_at: datetime
    previous_trend_observed_through: datetime
    m15_observed_through: datetime
    m5_observed_through: datetime
    previous_trend: TrendDirection
    m15_direction: TrendDirection
    m5_direction: TrendDirection
    source: str
    source_version: str | None = None

    def __post_init__(self) -> None:
        timestamp_fields = {
            "session_open_at": self.session_open_at,
            "available_at": self.available_at,
            "previous_trend_observed_through": self.previous_trend_observed_through,
            "m15_observed_through": self.m15_observed_through,
            "m5_observed_through": self.m5_observed_through,
        }
        for field_name, value in timestamp_fields.items():
            _require_aware(value, field_name=field_name)

        session_open_utc = self.session_open_at.astimezone(UTC)
        previous_utc = self.previous_trend_observed_through.astimezone(UTC)
        available_utc = self.available_at.astimezone(UTC)
        m15_utc = self.m15_observed_through.astimezone(UTC)
        m5_utc = self.m5_observed_through.astimezone(UTC)

        if previous_utc > session_open_utc:
            raise DirectionalContextDataError(
                "previous trend must be observed only from structure before the Opening Range"
            )
        if available_utc < max(previous_utc, m15_utc, m5_utc):
            raise DirectionalContextDataError(
                "directional context cannot be available before its latest observation"
            )
        if not self.source.strip():
            raise DirectionalContextDataError("directional context source must be recorded")
        if self.source_version is not None and not self.source_version.strip():
            raise DirectionalContextDataError("source_version cannot be blank when supplied")

    @property
    def source_identity(self) -> str:
        if self.source_version is None:
            return self.source
        return f"{self.source}@{self.source_version}"


class DirectionalContextProvider(Protocol):
    """Interface for retrieving directional context at a historical/live instant."""

    def get_snapshot(
        self,
        *,
        session: SessionKind,
        session_open_at: datetime,
        decision_at: datetime,
    ) -> ExternalDirectionalContextSnapshot:
        """Return context that was available no later than `decision_at`."""
        ...


@dataclass(frozen=True, slots=True)
class AcdDirectionalContext:
    """Validated directional context safe to consume at one decision instant."""

    session: SessionKind
    previous_trend: TrendDirection
    m15_direction: TrendDirection
    m5_direction: TrendDirection
    source: str
    available_at_utc: datetime
    previous_trend_observed_through_utc: datetime
    m15_observed_through_utc: datetime
    m5_observed_through_utc: datetime


def bind_directional_context(
    snapshot: ExternalDirectionalContextSnapshot,
    *,
    window: SessionWindow,
    decision_at: datetime,
) -> AcdDirectionalContext:
    """Validate and bind one external directional-context snapshot.

    The function deliberately does not infer trend from candles. Until the
    swing/ACD4 rules are frozen, sourced labels remain an explicit dependency.
    """

    _require_aware(decision_at, field_name="decision_at")

    decision_utc = decision_at.astimezone(UTC)
    snapshot_open_utc = snapshot.session_open_at.astimezone(UTC)
    available_utc = snapshot.available_at.astimezone(UTC)
    previous_utc = snapshot.previous_trend_observed_through.astimezone(UTC)
    m15_utc = snapshot.m15_observed_through.astimezone(UTC)
    m5_utc = snapshot.m5_observed_through.astimezone(UTC)

    if snapshot.session != window.session:
        raise DirectionalContextDataError("directional context belongs to a different session")
    if snapshot_open_utc != window.opens_at_utc:
        raise DirectionalContextDataError(
            "directional context session opening does not match session window"
        )
    if decision_utc < window.opening_range_ends_at_utc:
        raise DirectionalContextDataError(
            "directional context cannot authorize an ACD setup before the Opening Range is complete"
        )
    if available_utc > decision_utc:
        raise DirectionalContextDataError(
            "directional context snapshot was not available at decision time"
        )
    if max(previous_utc, m15_utc, m5_utc) > decision_utc:
        raise DirectionalContextDataError(
            "directional context contains observations from after decision time"
        )
    if previous_utc > window.opens_at_utc:
        raise DirectionalContextDataError(
            "previous trend observation extends into the current Opening Range"
        )

    return AcdDirectionalContext(
        session=snapshot.session,
        previous_trend=snapshot.previous_trend,
        m15_direction=snapshot.m15_direction,
        m5_direction=snapshot.m5_direction,
        source=snapshot.source_identity,
        available_at_utc=available_utc,
        previous_trend_observed_through_utc=previous_utc,
        m15_observed_through_utc=m15_utc,
        m5_observed_through_utc=m5_utc,
    )
