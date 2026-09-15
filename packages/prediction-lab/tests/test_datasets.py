from __future__ import annotations

import pandas as pd
import pytest

from prediction_lab.datasets import (
    DatasetFreezeError,
    freeze_cases,
    purged_temporal_group_split,
    temporal_question_split,
    verify_frozen_dataset,
)


def _cases() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "question_id": "q1",
                "question_text": "One?",
                "forecasted_at": "2025-12-01T00:00:00Z",
                "resolved_at": "2026-01-01T00:00:00Z",
                "market_price_timestamp": "2025-12-01T00:00:00Z",
                "source_cutoff_at": "2025-12-01T00:00:00Z",
                "market_probability": 0.4,
                "outcome": 0,
                "platform": "polymarket",
            },
            {
                "question_id": "q2",
                "question_text": "Two?",
                "forecasted_at": "2026-02-01T00:00:00Z",
                "resolved_at": "2026-03-01T00:00:00Z",
                "market_price_timestamp": "2026-02-01T00:00:00Z",
                "source_cutoff_at": "2026-02-01T00:00:00Z",
                "market_probability": 0.6,
                "outcome": 1,
                "platform": "kalshi",
            },
        ]
    )


def test_temporal_question_split_is_strict() -> None:
    development, holdout = temporal_question_split(
        _cases(),
        holdout_start="2026-01-01T00:00:00Z",
    )
    assert development["question_id"].tolist() == ["q1"]
    assert holdout["question_id"].tolist() == ["q2"]
    assert development["split"].tolist() == ["development"]
    assert holdout["split"].tolist() == ["holdout"]


def test_temporal_split_rejects_repeated_question() -> None:
    cases = pd.concat([_cases(), _cases().iloc[[0]]], ignore_index=True)
    with pytest.raises(DatasetFreezeError, match="one observation per question"):
        temporal_question_split(cases, holdout_start="2026-01-01T00:00:00Z")


def test_purged_temporal_group_split_removes_seen_parent_event_from_holdout() -> None:
    cases = pd.DataFrame(
        [
            {
                "question_id": "dev-a",
                "question_text": "Sibling A?",
                "forecasted_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-03-01T00:00:00Z",
                "market_price_timestamp": "2026-01-01T00:00:00Z",
                "source_cutoff_at": "2026-01-01T00:00:00Z",
                "market_probability": 0.4,
                "outcome": 0,
                "event_id": "event-shared",
            },
            {
                "question_id": "holdout-sibling",
                "question_text": "Sibling B?",
                "forecasted_at": "2026-02-01T00:00:00Z",
                "resolved_at": "2026-03-01T00:00:00Z",
                "market_price_timestamp": "2026-02-01T00:00:00Z",
                "source_cutoff_at": "2026-02-01T00:00:00Z",
                "market_probability": 0.5,
                "outcome": 1,
                "event_id": "event-shared",
            },
            {
                "question_id": "holdout-independent",
                "question_text": "Independent?",
                "forecasted_at": "2026-02-02T00:00:00Z",
                "resolved_at": "2026-03-02T00:00:00Z",
                "market_price_timestamp": "2026-02-02T00:00:00Z",
                "source_cutoff_at": "2026-02-02T00:00:00Z",
                "market_probability": 0.6,
                "outcome": 1,
                "event_id": "event-new",
            },
        ]
    )

    development, holdout = purged_temporal_group_split(
        cases,
        holdout_start="2026-02-01T00:00:00Z",
        group_column="event_id",
    )

    assert development["question_id"].tolist() == ["dev-a"]
    assert holdout["question_id"].tolist() == ["holdout-independent"]
    assert set(development["event_id"]).isdisjoint(set(holdout["event_id"]))


def test_frozen_dataset_round_trip_and_hash_check(tmp_path) -> None:
    csv_path = tmp_path / "cases.csv"
    manifest_path = tmp_path / "cases.manifest.json"

    manifest = freeze_cases(
        _cases(),
        csv_path=csv_path,
        manifest_path=manifest_path,
        source_name="prediction-market-analysis",
        source_revision="abc123",
        selection_policy="latest trade >=7d before resolution",
    )
    loaded = verify_frozen_dataset(csv_path=csv_path, manifest_path=manifest_path)

    assert manifest.row_count == 2
    assert manifest.question_count == 2
    assert len(loaded) == 2

    csv_path.write_text(csv_path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(DatasetFreezeError, match="hash mismatch"):
        verify_frozen_dataset(csv_path=csv_path, manifest_path=manifest_path)
