from datetime import date, timedelta

import pytest

from strategy_lab.core.levels import (
    AcdLevelDataError,
    ExternalAcdLevelSnapshot,
    bind_external_acd_levels,
)
from strategy_lab.core.models import SessionKind
from strategy_lab.core.opening_range import OpeningRange
from strategy_lab.core.sessions import SessionWindow, build_session_window


def _window() -> SessionWindow:
    return build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )


def _opening_range(window: SessionWindow) -> OpeningRange:
    return OpeningRange(
        starts_at_utc=window.opens_at_utc,
        ends_at_utc=window.opening_range_ends_at_utc,
        high=102.0,
        low=100.0,
        candle_count=40,
    )


def _snapshot(window: SessionWindow) -> ExternalAcdLevelSnapshot:
    return ExternalAcdLevelSnapshot(
        session=window.session,
        session_open_at=window.opens_at_utc,
        available_at=window.opening_range_ends_at_utc,
        a_up=104.0,
        c_up=106.0,
        a_down=98.0,
        c_down=96.0,
        source="trader-indicator",
        source_version="unknown-formula-v0.1",
    )


def test_external_levels_bind_to_independent_opening_range() -> None:
    window = _window()
    levels = bind_external_acd_levels(
        _snapshot(window),
        window=window,
        opening_range=_opening_range(window),
        decision_at=window.opening_range_ends_at_utc,
    )

    assert levels.or_up == 102.0
    assert levels.or_down == 100.0
    assert levels.a_up == 104.0
    assert levels.c_down == 96.0
    assert levels.source == "trader-indicator@unknown-formula-v0.1"


def test_snapshot_cannot_be_used_before_it_was_available() -> None:
    window = _window()
    snapshot = ExternalAcdLevelSnapshot(
        session=window.session,
        session_open_at=window.opens_at_utc,
        available_at=window.opening_range_ends_at_utc + timedelta(minutes=2),
        a_up=104.0,
        c_up=106.0,
        a_down=98.0,
        c_down=96.0,
        source="trader-indicator",
    )

    with pytest.raises(AcdLevelDataError, match="not available at decision time"):
        bind_external_acd_levels(
            snapshot,
            window=window,
            opening_range=_opening_range(window),
            decision_at=window.opening_range_ends_at_utc,
        )


def test_snapshot_cannot_claim_availability_before_or_completion() -> None:
    window = _window()
    snapshot = ExternalAcdLevelSnapshot(
        session=window.session,
        session_open_at=window.opens_at_utc,
        available_at=window.opening_range_ends_at_utc - timedelta(seconds=1),
        a_up=104.0,
        c_up=106.0,
        a_down=98.0,
        c_down=96.0,
        source="trader-indicator",
    )

    with pytest.raises(AcdLevelDataError, match="before OR completion"):
        bind_external_acd_levels(
            snapshot,
            window=window,
            opening_range=_opening_range(window),
            decision_at=window.opening_range_ends_at_utc,
        )


def test_snapshot_for_different_session_is_rejected() -> None:
    window = _window()
    snapshot = ExternalAcdLevelSnapshot(
        session=SessionKind.EUROPE_LONDON,
        session_open_at=window.opens_at_utc,
        available_at=window.opening_range_ends_at_utc,
        a_up=104.0,
        c_up=106.0,
        a_down=98.0,
        c_down=96.0,
        source="trader-indicator",
    )

    with pytest.raises(AcdLevelDataError, match="different session"):
        bind_external_acd_levels(
            snapshot,
            window=window,
            opening_range=_opening_range(window),
            decision_at=window.opening_range_ends_at_utc,
        )


def test_external_levels_must_fit_around_opening_range() -> None:
    window = _window()
    snapshot = ExternalAcdLevelSnapshot(
        session=window.session,
        session_open_at=window.opens_at_utc,
        available_at=window.opening_range_ends_at_utc,
        a_up=101.0,
        c_up=106.0,
        a_down=98.0,
        c_down=96.0,
        source="trader-indicator",
    )

    with pytest.raises(AcdLevelDataError, match="ACD levels must satisfy"):
        bind_external_acd_levels(
            snapshot,
            window=window,
            opening_range=_opening_range(window),
            decision_at=window.opening_range_ends_at_utc,
        )
