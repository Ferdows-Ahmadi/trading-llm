from datetime import UTC, date, datetime, timedelta

import pytest

from strategy_lab.core.context import (
    DirectionalContextDataError,
    ExternalDirectionalContextSnapshot,
    bind_directional_context,
)
from strategy_lab.core.models import SessionKind, TrendDirection
from strategy_lab.core.sessions import SessionWindow, build_session_window


def _window() -> SessionWindow:
    return build_session_window(
        SessionKind.AMERICA_NEW_YORK,
        date(2026, 9, 14),
        display_timezone="Asia/Kabul",
    )


def _snapshot(
    *,
    session: SessionKind | None = None,
    session_open_at: datetime | None = None,
    available_at: datetime | None = None,
    previous_trend_observed_through: datetime | None = None,
    m15_observed_through: datetime | None = None,
    m5_observed_through: datetime | None = None,
    previous_trend: TrendDirection = TrendDirection.BULLISH,
    m15_direction: TrendDirection = TrendDirection.BULLISH,
    m5_direction: TrendDirection = TrendDirection.BULLISH,
    source: str = "trader_annotation",
    source_version: str | None = "v1",
) -> ExternalDirectionalContextSnapshot:
    window = _window()
    effective_open = session_open_at or window.opens_at_utc
    effective_available = available_at or window.opening_range_ends_at_utc

    return ExternalDirectionalContextSnapshot(
        session=session or window.session,
        session_open_at=effective_open,
        available_at=effective_available,
        previous_trend_observed_through=(
            previous_trend_observed_through
            or effective_open - timedelta(minutes=1)
        ),
        m15_observed_through=m15_observed_through or effective_available,
        m5_observed_through=m5_observed_through or effective_available,
        previous_trend=previous_trend,
        m15_direction=m15_direction,
        m5_direction=m5_direction,
        source=source,
        source_version=source_version,
    )


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
    future_at = window.opening_range_ends_at_utc + timedelta(minutes=5)
    snapshot = _snapshot(
        available_at=future_at,
        m15_observed_through=future_at,
        m5_observed_through=future_at,
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
    before_or_end = window.opens_at_utc + timedelta(minutes=30)
    snapshot = _snapshot(
        available_at=before_or_end,
        m15_observed_through=before_or_end,
        m5_observed_through=before_or_end,
    )

    with pytest.raises(DirectionalContextDataError, match="before the Opening Range is complete"):
        bind_directional_context(
            snapshot,
            window=window,
            decision_at=before_or_end,
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
    equivalent_open = window.opens_at_utc.astimezone(window.opens_at_display.tzinfo)
    snapshot = _snapshot(session_open_at=equivalent_open)

    context = bind_directional_context(
        snapshot,
        window=window,
        decision_at=window.opening_range_ends_at_utc,
    )

    assert context.session is SessionKind.AMERICA_NEW_YORK


def test_utc_observation_times_are_preserved() -> None:
    window = _window()
    snapshot = _snapshot()

    context = bind_directional_context(
        snapshot,
        window=window,
        decision_at=window.opening_range_ends_at_utc,
    )

    assert context.available_at_utc.tzinfo is UTC
    assert context.m15_observed_through_utc.tzinfo is UTC
    assert context.m5_observed_through_utc.tzinfo is UTC
