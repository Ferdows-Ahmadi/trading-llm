from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pytest

from prediction_lab.datasets import freeze_cases
from prediction_lab.evidence import FixtureEvidenceProvider
from prediction_lab.experiments import run_development_experiment
from prediction_lab.research_forecaster import build_model_request
from prediction_lab.research_types import (
    EvidenceItem,
    EvidencePacket,
    ModelMetadata,
    ResearchContractError,
)


def _evidence_item(*, source_id: str, text: str) -> EvidenceItem:
    return EvidenceItem.create(
        source_id=source_id,
        source_type="archived-document",
        uri_or_reference="archive://retrieved-in-2026/item",
        title="Historical document",
        available_at="2025-01-01T00:00:00Z",
        retrieved_at="2026-09-10T00:00:00Z",
        text=text,
    )


def test_model_request_hides_operational_future_metadata() -> None:
    packet = EvidencePacket.create(
        question_id="q1",
        forecasted_at="2025-02-01T00:00:00Z",
        research_cutoff_at="2025-02-01T00:00:00Z",
        evidence_items=[_evidence_item(source_id="source-1", text="Known historical fact.")],
    )

    request = build_model_request(
        question_id="q1",
        question_text="Will the event happen?",
        evidence_packet=packet,
        prompt_version="research-v0",
        mode="blind",
        market_probability=None,
    )
    serialized = json.dumps(request, sort_keys=True)

    assert "retrieved_at" not in serialized
    assert "uri_or_reference" not in serialized
    assert "content_hash" not in serialized
    assert "packet_hash" not in serialized
    assert "2026-09-10" not in serialized
    assert request["evidence"] == {
        "evidence_items": [
            {
                "available_at": "2025-01-01T00:00:00.000000Z",
                "source_id": "source-1",
                "source_type": "archived-document",
                "text": "Known historical fact.",
                "title": "Historical document",
            }
        ],
        "forecasted_at": "2025-02-01T00:00:00.000000Z",
        "question_id": "q1",
        "research_cutoff_at": "2025-02-01T00:00:00.000000Z",
    }


class _FixedAdapter:
    def __init__(self, version: str) -> None:
        self.metadata = ModelMetadata.create(
            provider="test",
            model_id="fixed",
            immutable_version=version,
            release_date="2020-01-01T00:00:00Z",
            knowledge_cutoff="2020-01-01T00:00:00Z",
            execution_mode="local",
            contamination_assessment="historical-safe",
            contamination_notes="Deterministic regression-test adapter.",
        )

    def generate(self, request: Mapping[str, object]) -> Mapping[str, object]:
        evidence = request["evidence"]
        assert isinstance(evidence, dict)
        items = evidence["evidence_items"]
        assert isinstance(items, list)
        source_ids = [str(item["source_id"]) for item in items if isinstance(item, dict)]
        return {
            "base_rate_probability": 0.4,
            "updated_probability": 0.45,
            "final_probability": 0.43,
            "confidence_or_uncertainty": "test-only",
            "critique": "Deterministic regression output.",
            "cited_source_ids": source_ids,
        }


def _freeze_development(tmp_path: Path) -> tuple[Path, Path]:
    rows = []
    for index in range(4):
        forecasted_at = pd.Timestamp("2025-02-01T00:00:00Z") + pd.Timedelta(days=index)
        rows.append(
            {
                "question_id": f"q{index + 1}",
                "question_text": f"Will event {index + 1} happen?",
                "forecasted_at": forecasted_at,
                "resolved_at": forecasted_at + pd.Timedelta(days=30),
                "market_price_timestamp": forecasted_at,
                "source_cutoff_at": forecasted_at,
                "market_probability": 0.3 + index * 0.1,
                "outcome": index % 2,
                "category": "test",
                "event_id": f"event-{index + 1}",
                "split": "development",
            }
        )
    csv_path = tmp_path / "development.csv"
    manifest_path = tmp_path / "development.manifest.json"
    freeze_cases(
        pd.DataFrame(rows),
        csv_path=csv_path,
        manifest_path=manifest_path,
        source_name="regression-fixture",
        source_revision="v1",
        selection_policy="regression test only",
    )
    return csv_path, manifest_path


def _provider(text_suffix: str) -> FixtureEvidenceProvider:
    return FixtureEvidenceProvider(
        {
            f"q{index}": [
                _evidence_item(
                    source_id=f"source-{index}",
                    text=f"Evidence {index} {text_suffix}",
                )
            ]
            for index in range(1, 5)
        }
    )


def _run(
    *,
    csv_path: Path,
    manifest_path: Path,
    output_directory: Path,
    adapter: _FixedAdapter,
    provider: FixtureEvidenceProvider,
) -> tuple[dict[str, object], Path]:
    return run_development_experiment(
        development_csv=csv_path,
        development_manifest=manifest_path,
        evidence_provider=provider,
        adapter=adapter,
        output_directory=output_directory,
        experiment_id="identity-regression",
        hypothesis="Report identity must include result-affecting research inputs.",
        prompt_version="research-v0",
        mode="blind",
        repository_root=None,
    )


def test_report_identity_changes_with_model_and_evidence(tmp_path: Path) -> None:
    csv_path, manifest_path = _freeze_development(tmp_path)
    output_directory = tmp_path / "output"

    first, first_path = _run(
        csv_path=csv_path,
        manifest_path=manifest_path,
        output_directory=output_directory,
        adapter=_FixedAdapter("v1"),
        provider=_provider("alpha"),
    )
    changed_model, changed_model_path = _run(
        csv_path=csv_path,
        manifest_path=manifest_path,
        output_directory=output_directory,
        adapter=_FixedAdapter("v2"),
        provider=_provider("alpha"),
    )
    changed_evidence, changed_evidence_path = _run(
        csv_path=csv_path,
        manifest_path=manifest_path,
        output_directory=output_directory,
        adapter=_FixedAdapter("v1"),
        provider=_provider("beta"),
    )

    paths = {first_path, changed_model_path, changed_evidence_path}
    identities = {
        first["run_identity_hash"],
        changed_model["run_identity_hash"],
        changed_evidence["run_identity_hash"],
    }
    assert len(paths) == 3
    assert len(identities) == 3
    assert all(path.is_file() for path in paths)


def test_unsafe_model_fails_before_per_question_execution(tmp_path: Path) -> None:
    csv_path, manifest_path = _freeze_development(tmp_path)
    unsafe = _FixedAdapter("unsafe")
    unsafe.metadata = ModelMetadata.create(
        provider="test",
        model_id="unsafe",
        immutable_version="current",
        release_date="2026-01-01T00:00:00Z",
        knowledge_cutoff="2025-12-01T00:00:00Z",
        execution_mode="local",
        contamination_assessment="unknown",
        contamination_notes="Not defensible for historical scoring.",
    )

    with pytest.raises(ResearchContractError, match="historical-safe"):
        _run(
            csv_path=csv_path,
            manifest_path=manifest_path,
            output_directory=tmp_path / "unsafe-output",
            adapter=unsafe,
            provider=_provider("alpha"),
        )
