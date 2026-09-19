from prediction_lab.prospective_live_pilot_v01 import (
    TARGET_COHORT,
    select_structural_candidates,
)


def test_selector_keeps_one_market_per_event_and_is_deterministic() -> None:
    rows = [
        {"event_id": "e1", "market_id": "m1"},
        {"event_id": "e1", "market_id": "m2"},
        {"event_id": "e2", "market_id": "m3"},
        {"event_id": "e3", "market_id": "m4"},
    ]
    first = select_structural_candidates(rows)
    second = select_structural_candidates(list(reversed(rows)))
    assert [(row["event_id"], row["market_id"]) for row in first] == [
        (row["event_id"], row["market_id"]) for row in second
    ]
    assert len({row["event_id"] for row in first}) == len(first)
    assert len(first) == 3


def test_selector_caps_at_target() -> None:
    rows = [
        {"event_id": f"e{i}", "market_id": f"m{i}"}
        for i in range(TARGET_COHORT + 4)
    ]
    selected = select_structural_candidates(rows)
    assert len(selected) == TARGET_COHORT
    assert len({row["event_id"] for row in selected}) == TARGET_COHORT
