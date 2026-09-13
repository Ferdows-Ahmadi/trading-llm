from __future__ import annotations

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab import prospective_polymarket_custody_v03 as v03


def item(event_id: str, market_id: str) -> dict[str, object]:
    return {
        "event_id": event_id,
        "market_id": market_id,
        "ledger_index": 0,
    }


def test_v03_takes_at_most_two_deterministic_candidates_per_event() -> None:
    eligible = [
        item("event-a", "market-1"),
        item("event-a", "market-2"),
        item("event-a", "market-3"),
        item("event-b", "market-4"),
    ]

    candidates, groups = v03._deterministic_event_candidates(eligible)

    assert len(groups) == 2
    assert len(candidates) == 3
    assert sum(row["event_id"] == "event-a" for row in candidates) == 2
    assert sum(row["event_id"] == "event-b" for row in candidates) == 1
    assert {row["within_event_rank"] for row in candidates if row["event_id"] == "event-a"} == {1, 2}

    expected_a = sorted(
        [row for row in eligible if row["event_id"] == "event-a"],
        key=lambda row: base._rank(v03.SELECTION_SEED, row["event_id"], row["market_id"]),
    )[:2]
    assert [
        row["market_id"]
        for row in sorted(
            [row for row in candidates if row["event_id"] == "event-a"],
            key=lambda row: int(row["within_event_rank"]),
        )
    ] == [row["market_id"] for row in expected_a]


def test_v03_round_robin_prioritizes_first_candidates_before_seconds() -> None:
    rows = [
        {**item("event-a", "market-a1"), "within_event_rank": 1},
        {**item("event-a", "market-a2"), "within_event_rank": 2},
        {**item("event-b", "market-b1"), "within_event_rank": 1},
        {**item("event-b", "market-b2"), "within_event_rank": 2},
        {**item("event-c", "market-c1"), "within_event_rank": 1},
    ]

    selected = v03._select_clustered_cohort(rows)

    first_positions = [
        index for index, row in enumerate(selected) if row["within_event_rank"] == 1
    ]
    second_positions = [
        index for index, row in enumerate(selected) if row["within_event_rank"] == 2
    ]
    assert max(first_positions) < min(second_positions)
    assert len(selected) == len(rows)


def test_v03_round_rank_is_deterministic() -> None:
    row = {**item("event-a", "market-a1"), "within_event_rank": 1}
    expected = base._rank(
        v03.SELECTION_SEED,
        1,
        "event-a",
        "market-a1",
    )
    assert v03._round_rank(row) == expected
    assert v03._round_rank(row) == expected


def test_v03_frozen_identity_and_gates() -> None:
    assert v03.PROTOCOL_COMMIT == "a4de3487a3c931b9e04578b7a501aabb6050e0cc"
    assert v03.SELECTION_SEED == (
        "prospective-development-custody-v0.3-selection-seed-2026-09-13"
    )
    assert v03.TARGET_COHORT == 80
    assert v03.MAX_PER_EVENT == 2
    assert v03.MARKET_FLOOR == 60
    assert v03.EVENT_CLUSTER_FLOOR == 40
    assert str(v03.MIN_HORIZON) == "7 days 00:00:00"
    assert str(v03.MAX_HORIZON) == "90 days 00:00:00"
