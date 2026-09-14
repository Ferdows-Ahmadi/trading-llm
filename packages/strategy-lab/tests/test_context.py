from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_lab.core.context import (
    DirectionalContextDataError,
    ExternalDirectionalContextSnapshot,
    bind_directional_context,
)
from strategy_lab.core.models import SessionKind, TrendDirection
from strategy_lab.core.sessions import build_session_window


def _window():
    return build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )


def _snapshot(**overrides):
    window = _window()
    values = {
        "session": window.session,
        "session_open_at": window.opens_at_utc,
        "available_at": window.opening_range_ends_at_utc,
        "previous_trend_observed_through": window.opens_at_utc - timedelta(minutes=1),
        "m15_observed_through": window.opening_range_ends_at_utc,
        "m5_observed_through": window.opening_range_ends_at_utc,
        "previous_trend": TrendDirection.BULLISH,
        "m15_direction": TrendDirection.BULLISH,
        "m5_direction": TrendDirection.BULLISH,
        "source": "trader_annotation",
        "source_version": "v1",
    }
    values.update(overrides)
    return ExternalDirectionalContextSnapshot(**values)


def test_valid_directional_context_binds_after_opening_range() -> None:
    window = _window()
    snapshot = _snapshot()

    context = bind_directional_context(
        snapshot,
        window=window,
        decision_at=window.opening_range_ends_at_utc,
    )

    assert context.previous_trend is TrendDirection.BULLISH
    assert context.m15_direction is TrendDirection.BULLISH
    assert context.m5_direction is TrendDirection.BULLISH
    assert context.source == "trader_annotation@v1"


def test_unclear_and_unresolved_states_are_preserved() -> None:
    window = _window()
    snapshot = _snapshot(
        previous_trend=TrendDirection.UNCLEAR,
        m15_direction=TrendDirection.UNRESOLVED,
        m5_direction=TrendDirection.UNCLEAR,
    )

    context = bind_directional_context(
        snapshot,
        window=window,
        decision_at=window.opening_range_ends_at_utc,
    )

    assert context.previous_trend is TrendDirection.UNCLEAR
    assert context.m15_direction is TrendDirection.UNRESOLVED
    assert context.m5_direction is TrendDirection.UNCLEAR


def test_previous_trend_cannot_use_current_opening_range() -> None:
    window = _window()

    with pytest.raises(DirectionalContextDataError, match="before the Opening Range"):
        _snapshot(previous_trend_observed_through=window.opens_at_utc + timedelta(minutes=1))


def test_snapshot_cannot_be_available_before_latest_observation() -> None:
    window = _window()

    with pytest.raises(DirectionalContextDataError, match="latest observation"):
        _snapshot(
            available_at=window.opening_range_ends_at_utc - timedelta(minutes=1),
            m15_observed_through=window.opening_range_ends_at_utc,
        )


def test_future_snapshot_is_rejected_at_decision_time() -> None:
    window = _window()
    snapshot = _snapshot(
        available_at=window.opening_range_ends_at_utc + timedelta(minutes=5),
        m15_observed_through=window.opening_range_ends_at_utc + timedelta(minutes=5),
        m5_observed_through=window.opening_range_ends_at_utc + timedelta(minutes=5),
    )

    with pytest.raises(DirectionalContextDataError, match="not available at decision time"):
        bind_directional_context(
            snapshot,
            window=window,
            decision_at=window.opening_range_ends_at_utc,
        )


def test_mismatched_session_is_rejected() -> None:
    window = _window()
    snapshot = _snapshot(session=SessionKind.EUROPE_LONDON)

    with pytest.raises(DirectionalContextDataError, match="different session"):
        bind_directional_context(
            snapshot,
            window=window,
            decision_at=window.opening_range_ends_at_utc,
        )


def test_mismatched_session_open_is_rejected() -> None:
    window = _window()
    snapshot = _snapshot(session_open_at=window.opens_at_utc - timedelta(days=1))

    with pytest.raises(DirectionalContextDataError, match="opening does not match"):
        bind_directional_context(
            snapshot,
            window=window,
            decision_at=window.opening_range_ends_at_utc,
        )


def test_context_cannot_authorize_setup_before_opening_range_complete() -> None:
    window = _window()
    snapshot = _snapshot(
        available_at=window.opens_at_utc + timedelta(minutes=30),
        m15_observed_through=window.opens_at_utc + timedelta(minutes=30),
        m5_observed_through=window.opens_at_utc + timedelta(minutes=30),
    )

    with pytest.raises(DirectionalContextDataError, match="before the Opening Range is complete"):
        bind_directional_context(
            snapshot,
            window=window,
            decision_at=window.opens_at_utc + timedelta(minutes=30),
        )


def test_naive_decision_timestamp_is_rejected() -> None:
    window = _window()
    snapshot = _snapshot()

    with pytest.raises(DirectionalContextDataError, match="timezone-aware"):
        bind_directional_context(
            snapshot,
            window=window,
            decision_at=datetime(2026, 9, 14, 14, 10),  # noqa: DTZ001 - intentional negative test
        )


def test_timezone_equivalent_session_open_is_accepted() -> None:
    window = _window()
    equivalent_open = datetime(2026, 9, 14, 9, 30, tzinfo=UTC).astimezone(
        window.opens_at_display.tzinfo
    )
    snapshot = _snapshot(session_open_at=equivalent_open)

    context = bind_directional_context(
        snapshot,
        window=window,
        decision_at=window.opening_range_ends_at_utc,
    )

    assert context.session is SessionKind.AMERICA_NEW_YORK
