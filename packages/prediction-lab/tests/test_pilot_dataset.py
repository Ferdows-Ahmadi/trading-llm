from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from prediction_lab.datasets import DatasetFreezeError, freeze_cases, verify_frozen_dataset
from prediction_lab.pilot_dataset import build_development_pilot


def _development_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(4):
        forecasted = pd.Timestamp("2025-01-01T00:00:00Z") + pd.Timedelta(days=index)
        rows.append(
            {
                "category": "crypto",
                "event_id": f"event-{index}",
                "forecasted_at": forecasted,
                "market_price_timestamp": forecasted - pd.Timedelta(hours=1),
                "market_probability": 0.2 + index * 0.1,
                "outcome": index % 2,
                "question_id": f"q{index}",
                "question_text": f"Question {index}?",
                "resolved_at": forecasted + pd.Timedelta(days=7),
                "source_cutoff_at": forecasted,
                "split": "development",
            }
        )
    return pd.DataFrame(rows)


def test_build_development_pilot_freezes_exact_discovery_ids(tmp_path: Path) -> None:
    source_csv = tmp_path / "development.csv"
    source_manifest = tmp_path / "development.manifest.json"
    freeze_cases(
        _development_frame(),
        csv_path=source_csv,
        manifest_path=source_manifest,
        source_name="fixture",
        source_revision="fixture-v1",
        selection_policy="fixture",
    )
    discovery = tmp_path / "discovery.jsonl"
    discovery.write_text(
        json.dumps({"question_id": "q1"})
        + "\n"
        + json.dumps({"question_id": "q3"})
        + "\n",
        encoding="utf-8",
    )

    output_csv = tmp_path / "pilot.csv"
    output_manifest = tmp_path / "pilot.manifest.json"
    manifest = build_development_pilot(
        development_csv=source_csv,
        development_manifest=source_manifest,
        discovery_jsonl=discovery,
        output_csv=output_csv,
        output_manifest=output_manifest,
        expected_question_count=2,
    )

    assert manifest.row_count == 2
    assert manifest.question_count == 2
    assert "no outcome-based selection" in manifest.selection_policy
    frozen = verify_frozen_dataset(csv_path=output_csv, manifest_path=output_manifest)
    assert set(frozen["question_id"].astype(str)) == {"q1", "q3"}
    assert set(frozen["split"].astype(str)) == {"development"}


def test_build_development_pilot_rejects_missing_ids(tmp_path: Path) -> None:
    source_csv = tmp_path / "development.csv"
    source_manifest = tmp_path / "development.manifest.json"
    freeze_cases(
        _development_frame(),
        csv_path=source_csv,
        manifest_path=source_manifest,
        source_name="fixture",
        source_revision="fixture-v1",
        selection_policy="fixture",
    )
    discovery = tmp_path / "discovery.jsonl"
    discovery.write_text(json.dumps({"question_id": "missing"}) + "\n", encoding="utf-8")

    with pytest.raises(DatasetFreezeError, match="missing from development"):
        build_development_pilot(
            development_csv=source_csv,
            development_manifest=source_manifest,
            discovery_jsonl=discovery,
            output_csv=tmp_path / "pilot.csv",
            output_manifest=tmp_path / "pilot.manifest.json",
        )
