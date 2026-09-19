from __future__ import annotations

import json
import socket
import sys
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pytest

from prediction_lab.datasets import freeze_cases
from prediction_lab.evidence import FileEvidenceProvider, FixtureEvidenceProvider
from prediction_lab.experiments import (
    inner_development_validation_split,
    run_development_experiment,
)
from prediction_lab.research_cache import FilesystemForecastCache, forecast_cache_key
from prediction_lab.research_cli import main as research_cli_main
from prediction_lab.research_forecaster import (
    DeterministicFakeModelAdapter,
    forecast_question,
)
from prediction_lab.research_types import (
    EvidenceItem,
    EvidencePacket,
    ForecastArtifact,
    ModelMetadata,
    ResearchContractError,
)


def _item(
    *, source_id: str = "source-1", text: str = "Evidence known before the forecast."
) -> EvidenceItem:
    return EvidenceItem.create(
        source_id=source_id,
        source_type="fixture",
        uri_or_reference=f"fixture://{source_id}",
        title="Historical fixture",
        available_at="2025-01-01T00:00:00Z",
        retrieved_at="2026-09-10T00:00:00Z",
        text=text,
    )


def _packet(*, question_id: str = "q1", text: str = "Evidence.") -> EvidencePacket:
    return EvidencePacket.create(
        question_id=question_id,
        forecasted_at="2025-02-01T00:00:00Z",
        research_cutoff_at="2025-02-01T00:00:00Z",
        evidence_items=[_item(text=text)],
    )


def _safe_metadata(*, version: str = "v1") -> ModelMetadata:
    return ModelMetadata.create(
        provider="test",
        model_id="model",
        immutable_version=version,
        release_date="2020-01-01T00:00:00Z",
        knowledge_cutoff="2020-01-01T00:00:00Z",
        execution_mode="local",
        contamination_assessment="historical-safe",
        contamination_notes="Frozen deterministic test model.",
    )


def _valid_output() -> dict[str, object]:
    return {
        "base_rate_probability": 0.4,
        "updated_probability": 0.45,
        "final_probability": 0.43,
        "confidence_or_uncertainty": "low confidence",
        "critique": "Evidence is sparse.",
        "cited_source_ids": ["source-1"],
    }


class _RecordingAdapter:
    def __init__(
        self,
        *,
        output: Mapping[str, object] | None = None,
        metadata: ModelMetadata | None = None,
    ) -> None:
        self.metadata = metadata or _safe_metadata()
        self.output = dict(output or _valid_output())
        self.requests: list[Mapping[str, object]] = []

    def generate(self, request: Mapping[str, object]) -> Mapping[str, object]:
        self.requests.append(request)
        return self.output


def _forecast(
    tmp_path: Path,
    *,
    adapter: _RecordingAdapter,
    mode: str,
    market_probability: float | None,
    prompt_version: str = "prompt-v1",
    question_text: str = "Will the event happen?",
) -> ForecastArtifact:
    artifact, _ = forecast_question(
        experiment_id="experiment-1",
        benchmark_hash="benchmark-hash",
        code_commit="commit-sha",
        experiment_config_hash="config-hash",
        question_id="q1",
        question_text=question_text,
        evidence_packet=_packet(),
        prompt_version=prompt_version,
        mode=mode,  # type: ignore[arg-type]
        market_probability=market_probability,
        adapter=adapter,
        cache=FilesystemForecastCache(tmp_path / "cache"),
    )
    return artifact


def _cases() -> pd.DataFrame:
    rows = []
    groups = ["shared", "early", "shared", "late"]
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
                "market_probability": 0.2 + index * 0.15,
                "outcome": index % 2,
                "category": "test",
                "event_id": groups[index],
                "split": "development",
            }
        )
    return pd.DataFrame(rows)


def _frozen_cases(tmp_path: Path) -> tuple[Path, Path]:
    csv_path = tmp_path / "development.csv"
    manifest_path = tmp_path / "development.manifest.json"
    freeze_cases(
        _cases(),
        csv_path=csv_path,
        manifest_path=manifest_path,
        source_name="test-source",
        source_revision="fixture-v1",
        selection_policy="test-only development fixture",
    )
    return csv_path, manifest_path


def _provider() -> FixtureEvidenceProvider:
    return FixtureEvidenceProvider(
        {f"q{index}": [_item(source_id=f"source-{index}")] for index in range(1, 5)}
    )


def test_evidence_newer_than_forecast_cutoff_is_rejected() -> None:
    item = EvidenceItem.create(
        source_id="future",
        source_type="fixture",
        uri_or_reference="fixture://future",
        title="Future evidence",
        available_at="2025-02-02T00:00:00Z",
        retrieved_at="2026-09-10T00:00:00Z",
        text="Not available yet.",
    )
    with pytest.raises(ResearchContractError, match="newer than research cutoff"):
        EvidencePacket.create(
            question_id="q1",
            forecasted_at="2025-02-01T00:00:00Z",
            research_cutoff_at="2025-02-01T00:00:00Z",
            evidence_items=[item],
        )


def test_missing_or_unknown_evidence_availability_is_rejected(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "questions": {
            "q1": [
                {
                    "source_id": "source-1",
                    "source_type": "fixture",
                    "uri_or_reference": "fixture://source-1",
                    "title": "Missing time",
                    "retrieved_at": "2026-09-10T00:00:00Z",
                    "text": "No defensible availability timestamp.",
                }
            ]
        },
    }
    fixture_path = tmp_path / "evidence.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResearchContractError, match="available_at must be a known timestamp"):
        FileEvidenceProvider(fixture_path)


def test_blind_and_market_aware_requests_enforce_information_boundaries(tmp_path: Path) -> None:
    blind = _RecordingAdapter()
    blind_artifact = _forecast(
        tmp_path / "blind", adapter=blind, mode="blind", market_probability=None
    )
    blind_request = blind.requests[0]
    assert blind_artifact.blind_or_market_aware == "blind"
    assert "market_probability" not in blind_request
    assert "outcome" not in json.dumps(blind_request)
    assert "resolved_at" not in json.dumps(blind_request)

    aware = _RecordingAdapter()
    aware_artifact = _forecast(
        tmp_path / "aware",
        adapter=aware,
        mode="market-aware",
        market_probability=0.63,
    )
    aware_request = aware.requests[0]
    assert aware_artifact.blind_or_market_aware == "market-aware"
    assert aware_request["market_probability"] == 0.63
    assert "market_price_timestamp" not in json.dumps(aware_request)
    assert "outcome" not in json.dumps(aware_request)
    assert "resolved_at" not in json.dumps(aware_request)


def test_malformed_structured_model_output_fails_loudly(tmp_path: Path) -> None:
    adapter = _RecordingAdapter(output={"final_probability": 0.5})
    with pytest.raises(ResearchContractError, match="Malformed structured model output"):
        _forecast(tmp_path, adapter=adapter, mode="blind", market_probability=None)


def test_historical_model_contamination_fails_closed(tmp_path: Path) -> None:
    unsafe = ModelMetadata.create(
        provider="api",
        model_id="current-model",
        immutable_version="unknown",
        release_date="2026-01-01T00:00:00Z",
        knowledge_cutoff="2025-12-31T00:00:00Z",
        execution_mode="api",
        contamination_assessment="unknown",
        contamination_notes="Cannot rule out knowledge of historical outcomes.",
    )
    adapter = _RecordingAdapter(metadata=unsafe)
    with pytest.raises(ResearchContractError, match="historical-safe"):
        _forecast(tmp_path, adapter=adapter, mode="blind", market_probability=None)
    assert adapter.requests == []


def test_cache_key_changes_for_every_result_affecting_boundary() -> None:
    packet_one = _packet(text="One")
    packet_two = _packet(text="Two")

    def key(
        *,
        packet: EvidencePacket = packet_one,
        prompt: str = "p1",
        model: ModelMetadata | None = None,
        mode: str = "blind",
        request_hash: str = "request-1",
        code_commit: str = "commit-1",
    ) -> str:
        return forecast_cache_key(
            code_commit=code_commit,
            model_request_hash=request_hash,
            evidence_packet_hash=packet.packet_hash,
            prompt_version=prompt,
            model_metadata=(model or _safe_metadata()).to_dict(),
            mode=mode,
            experiment_config_hash="config-1",
        )

    baseline = key()
    assert key(packet=packet_two) != baseline
    assert key(prompt="p2") != baseline
    assert key(model=_safe_metadata(version="v2")) != baseline
    assert key(mode="market-aware") != baseline
    assert key(request_hash="request-2") != baseline
    assert key(code_commit="commit-2") != baseline


def test_cache_rejects_packet_newer_than_current_cutoff(tmp_path: Path) -> None:
    cache = FilesystemForecastCache(tmp_path)
    with pytest.raises(ResearchContractError, match="newer than forecast cutoff"):
        cache.load(
            "0" * 64,
            evidence_packet=_packet(),
            forecast_cutoff_at="2024-12-31T00:00:00Z",
        )


def test_cache_key_tracks_question_text_and_market_probability(tmp_path: Path) -> None:
    first = _forecast(
        tmp_path,
        adapter=_RecordingAdapter(),
        mode="market-aware",
        market_probability=0.4,
    )
    changed_market = _forecast(
        tmp_path,
        adapter=_RecordingAdapter(),
        mode="market-aware",
        market_probability=0.5,
    )
    changed_question = _forecast(
        tmp_path,
        adapter=_RecordingAdapter(),
        mode="market-aware",
        market_probability=0.4,
        question_text="Will a different event happen?",
    )
    assert len({first.cache_key, changed_market.cache_key, changed_question.cache_key}) == 3


def test_parent_event_groups_do_not_cross_inner_split() -> None:
    development, validation, _ = inner_development_validation_split(
        _cases(), validation_fraction=0.5
    )
    assert set(development["event_id"]).isdisjoint(set(validation["event_id"]))
    assert "q3" not in validation["question_id"].tolist()


def test_failed_forecasts_remain_in_experiment_denominator(tmp_path: Path) -> None:
    csv_path, manifest_path = _frozen_cases(tmp_path)
    summary, _ = run_development_experiment(
        development_csv=csv_path,
        development_manifest=manifest_path,
        evidence_provider=_provider(),
        adapter=DeterministicFakeModelAdapter(fail_question_ids=frozenset({"q2"})),
        output_directory=tmp_path / "output",
        experiment_id="failure-accounting",
        hypothesis="The runner counts every attempted development question.",
        prompt_version="research-v0",
        mode="blind",
    )
    assert summary["execution"] == {
        "failed_forecasts": 1,
        "forecast_coverage": 0.75,
        "successful_forecasts": 3,
        "total_questions": 4,
    }
    assert summary["evaluation"]["sample_size"] == 3
    assert summary["failures"][0]["question_id"] == "q2"


def test_development_runner_rejects_holdout_split(tmp_path: Path) -> None:
    csv_path = tmp_path / "holdout.csv"
    manifest_path = tmp_path / "holdout.manifest.json"
    freeze_cases(
        _cases().assign(split="holdout"),
        csv_path=csv_path,
        manifest_path=manifest_path,
        source_name="test-source",
        source_revision="fixture-v1",
        selection_policy="test-only holdout fixture",
    )
    with pytest.raises(ResearchContractError, match="explicitly development"):
        run_development_experiment(
            development_csv=csv_path,
            development_manifest=manifest_path,
            evidence_provider=_provider(),
            adapter=DeterministicFakeModelAdapter(),
            output_directory=tmp_path / "output",
            experiment_id="must-not-run",
            hypothesis="Holdout data must fail at the development boundary.",
            prompt_version="research-v0",
            mode="blind",
        )


def test_fake_model_experiment_is_byte_reproducible_and_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path, manifest_path = _frozen_cases(tmp_path)

    def network_forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("normal experiment CI must not open network sockets")

    monkeypatch.setattr(socket, "socket", network_forbidden)
    arguments = {
        "development_csv": csv_path,
        "development_manifest": manifest_path,
        "evidence_provider": _provider(),
        "output_directory": tmp_path / "output",
        "experiment_id": "reproducibility",
        "hypothesis": "The deterministic fake adapter validates machinery, not edge.",
        "prompt_version": "research-v0",
        "mode": "market-aware",
    }
    first, first_path = run_development_experiment(
        adapter=DeterministicFakeModelAdapter(),
        **arguments,  # type: ignore[arg-type]
    )
    first_bytes = first_path.read_bytes()
    second, second_path = run_development_experiment(
        adapter=DeterministicFakeModelAdapter(),
        **arguments,  # type: ignore[arg-type]
    )
    assert first == second
    assert first_path == second_path
    assert first_bytes == second_path.read_bytes()


def test_development_cli_runs_end_to_end_with_file_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    csv_path, manifest_path = _frozen_cases(tmp_path)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "questions": {
                    f"q{index}": [_item(source_id=f"source-{index}").to_dict()]
                    for index in range(1, 5)
                },
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "cli-output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prediction-lab-research",
            str(csv_path),
            str(manifest_path),
            str(evidence_path),
            str(output_path),
            "--experiment-id",
            "cli-smoke",
            "--hypothesis",
            "The CLI exercises only deterministic offline machinery.",
            "--mode",
            "blind",
        ],
    )
    research_cli_main()
    output = json.loads(capsys.readouterr().out)
    assert output["execution"]["total_questions"] == 4
    assert output["execution"]["failed_forecasts"] == 0
    assert Path(output["report_path"]).is_file()
