"""Timezone-safe regional session definitions for ACD v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import SessionKind

OPENING_RANGE_DURATION = timedelta(minutes=40)


@dataclass(frozen=True, slots=True)
class SessionDefinition:
    kind: SessionKind
    home_timezone: str
    opening_time: time


@dataclass(frozen=True, slots=True)
class SessionWindow:
    session: SessionKind
    home_timezone: str
    display_timezone: str
    opens_at_utc: datetime
    opening_range_ends_at_utc: datetime
    opens_at_display: datetime
    opening_range_ends_at_display: datetime


SESSION_DEFINITIONS: dict[SessionKind, SessionDefinition] = {
    SessionKind.ASIA_SINGAPORE: SessionDefinition(
        kind=SessionKind.ASIA_SINGAPORE,
        home_timezone="Asia/Singapore",
        opening_time=time(hour=9, minute=0),
    ),
    SessionKind.EUROPE_LONDON: SessionDefinition(
        kind=SessionKind.EUROPE_LONDON,
        home_timezone="Europe/London",
        opening_time=time(hour=8, minute=0),
    ),
    SessionKind.AMERICA_NEW_YORK: SessionDefinition(
        kind=SessionKind.AMERICA_NEW_YORK,
        home_timezone="America/New_York",
        opening_time=time(hour=9, minute=30),
    ),
}


def build_session_window(
    session: SessionKind,
    session_date: date,
    *,
    display_timezone: str = "UTC",
) -> SessionWindow:
    """Build one session opening and 40-minute OR window.

    `session_date` is interpreted in the session's own home timezone. IANA
    timezone conversion handles DST automatically.
    """

    definition = SESSION_DEFINITIONS[session]
    home_zone = ZoneInfo(definition.home_timezone)
    display_zone = ZoneInfo(display_timezone)

    local_open = datetime.combine(
        session_date,
        definition.opening_time,
        tzinfo=home_zone,
    )
    local_or_end = local_open + OPENING_RANGE_DURATION

    open_utc = local_open.astimezone(UTC)
    or_end_utc = local_or_end.astimezone(UTC)

    return SessionWindow(
        session=session,
        home_timezone=definition.home_timezone,
        display_timezone=display_timezone,
        opens_at_utc=open_utc,
        opening_range_ends_at_utc=or_end_utc,
        opens_at_display=open_utc.astimezone(display_zone),
        opening_range_ends_at_display=or_end_utc.astimezone(display_zone),
    )
