from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from prediction_lab.datasets import freeze_cases
from prediction_lab.evidence_discovery_stage import run_gdelt_discovery_stage
from prediction_lab.gdelt_evidence import GdeltArticle


@dataclass
class FakeDiscovery:
    calls: int = 0

    def search(
        self,
        question_text: str,
        *,
        cutoff: pd.Timestamp,
        lookback_days: int,
        max_records: int,
    ) -> list[GdeltArticle]:
        del lookback_days, max_records
        self.calls += 1
        return [
            GdeltArticle(
                title=f"Historical reporting for {question_text}",
                url=f"https://example.com/{self.calls}",
                seen_at=cutoff - pd.Timedelta(hours=1),
                domain="example.com",
                language="English",
                source_country="United States",
            )
        ]


def _freeze_development(tmp_path: Path) -> tuple[Path, Path]:
    rows = []
    for index in range(4):
        forecasted = pd.Timestamp("2025-10-01T12:00:00Z") + pd.Timedelta(days=index)
        rows.append(
            {
                "question_id": f"q-{index}",
                "question_text": f"Will event {index} happen?",
                "forecasted_at": forecasted,
                "resolved_at": forecasted + pd.Timedelta(days=10),
                "market_price_timestamp": forecasted,
                "source_cutoff_at": forecasted,
                "market_probability": 0.5,
                "outcome": index % 2,
                "event_id": f"event-{index}",
                "split": "development",
            }
        )

    csv_path = tmp_path / "development.csv"
    manifest_path = tmp_path / "development.manifest.json"
    freeze_cases(
        pd.DataFrame(rows),
        csv_path=csv_path,
        manifest_path=manifest_path,
        source_name="test",
        source_revision="test-revision",
        selection_policy="test development fixture",
    )
    return csv_path, manifest_path


def test_discovery_stage_reuses_atomic_question_checkpoints(tmp_path: Path) -> None:
    csv_path, manifest_path = _freeze_development(tmp_path)
    output = tmp_path / "discovery"
    provider = FakeDiscovery()

    first_summary, first_audit = run_gdelt_discovery_stage(
        development_csv=csv_path,
        development_manifest=manifest_path,
        output_directory=output,
        discovery=provider,
        pilot_size=4,
        lookback_days=30,
        max_records=5,
    )
    assert provider.calls == 4
    assert first_summary["questions_with_results"] == 4
    assert first_summary["reused_checkpoints"] == 0
    assert len(first_audit) == 4

    second_summary, second_audit = run_gdelt_discovery_stage(
        development_csv=csv_path,
        development_manifest=manifest_path,
        output_directory=output,
        discovery=provider,
        pilot_size=4,
        lookback_days=30,
        max_records=5,
    )
    assert provider.calls == 4
    assert second_summary["attempted_this_run"] == 0
    assert second_summary["reused_checkpoints"] == 4
    assert second_audit.equals(first_audit)
    assert (output / "discovery.jsonl").exists()
