from datetime import date, timedelta

from strategy_lab.core.models import SessionKind
from strategy_lab.core.sessions import build_session_window


def test_september_2026_kabul_session_times() -> None:
    asia = build_session_window(
        SessionKind.ASIA_SINGAPORE,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )
    london = build_session_window(
        SessionKind.EUROPE_LONDON,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )
    new_york = build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )

    assert (asia.opens_at_display.hour, asia.opens_at_display.minute) == (5, 30)
    assert (london.opens_at_display.hour, london.opens_at_display.minute) == (11, 30)
    assert (new_york.opens_at_display.hour, new_york.opens_at_display.minute) == (18, 0)


def test_winter_2026_kabul_session_times_follow_dst() -> None:
    london = build_session_window(
        SessionKind.EUROPE_LONDON,
        date(2026, 12, 1),
        display_timezone="Asia/Kabul",
    )
    new_york = build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 12, 1),
        display_timezone="Asia/Kabul",
    )

    assert (london.opens_at_display.hour, london.opens_at_display.minute) == (12, 30)
    assert (new_york.opens_at_display.hour, new_york.opens_at_display.minute) == (19, 0)


def test_opening_range_is_exactly_40_minutes() -> None:
    window = build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="America/New_York",
    )

    assert window.opening_range_ends_at_utc - window.opens_at_utc == timedelta(minutes=40)
    assert (
        window.opening_range_ends_at_display - window.opens_at_display
        == timedelta(minutes=40)
    )
