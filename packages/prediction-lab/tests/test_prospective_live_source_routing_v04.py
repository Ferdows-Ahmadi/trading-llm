from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prediction_lab import prospective_live_source_routing_session_v04 as session
from prediction_lab import prospective_live_source_routing_v04 as selector
from prediction_lab.research_types import ResearchContractError


def _eligible(market_id: int, event_id: int) -> dict[str, object]:
    return {"market_id": str(market_id), "event_id": str(event_id)}


def test_v04_selector_identity_and_event_uniqueness_are_frozen() -> None:
    assert selector.PROTOCOL_COMMIT == "24cb23281b0331ba5cbd3159cfc378733350248c"
    assert selector.MODEL_MANIFEST_SHA256 == (
        "3cac3f0949f844e39fb052d104d2a284f4eeef2ba3c1674263c2ba99c4bfa514"
    )
    assert selector.SELECTION_SEED == (
        "prospective-live-source-routing-v0.4-selection-seed-2026-09-19"
    )
    assert selector.TARGET_COHORT == 12
    rows = [_eligible(index, index // 2) for index in range(40)]
    first = selector.select_structural_candidates(rows)  # type: ignore[arg-type]
    second = selector.select_structural_candidates(list(reversed(rows)))  # type: ignore[arg-type]
    assert first == second
    assert len(first) == 12
    assert len({str(row["event_id"]) for row in first}) == 12


def test_v04_exact_model_identities_are_bound_to_preselection_freeze() -> None:
    assert selector.FROZEN_MODELS == (
        (
            "llama3.1:8b",
            "sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
        ),
        (
            "qwen3.5:9b",
            "sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7",
        ),
        (
            "deepseek-r1:8b",
            "sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763",
        ),
    )
    assert session.FROZEN_MODELS == selector.FROZEN_MODELS
    assert session.CONDITIONS == ("condition-a", "condition-b")
    assert session.ACQUISITION_SUCCESS_FLOOR == 10


class _StatefulFakeAdapter:
    instances: list[_StatefulFakeAdapter] = []

    def __init__(self, **_: object) -> None:
        self.decisions: dict[str, dict[str, object]] = {}
        self.fail_next = False
        type(self).instances.append(self)

    def generate(self, request: dict[str, object]) -> dict[str, object]:
        question = request["question"]
        assert isinstance(question, dict)
        question_id = str(question["question_id"])
        if question_id in self.decisions:
            raise AssertionError("adapter state was reused across paired conditions")
        if self.fail_next:
            self.fail_next = False
            raise ResearchContractError("synthetic single-cell model failure")
        prior = float(request["market_probability"])
        self.decisions[question_id] = {
            "action": "abstain",
            "evidence_strength": "none",
            "final_probability": prior,
            "hard_noop": False,
            "logit_delta": 0.0,
            "mapping_version": "logit-residual-v1",
            "market_probability": prior,
            "raw_model_output": {},
        }
        return {
            "base_rate_probability": prior,
            "updated_probability": prior,
            "final_probability": prior,
            "confidence_or_uncertainty": "test uncertainty",
            "critique": "test critique",
            "cited_source_ids": [],
        }

    def decision_records(self) -> dict[str, dict[str, object]]:
        return {key: dict(value) for key, value in self.decisions.items()}

    def close(self) -> None:
        pass


def _evidence_item(index: int, condition: str, timestamp: str) -> dict[str, str]:
    return {
        "source_id": f"test:{condition}:{index}",
        "source_type": "test-evidence",
        "uri_or_reference": f"https://example.test/{condition}/{index}",
        "title": f"Evidence {condition} {index}",
        "available_at": timestamp,
        "text": f"Decision relevant evidence for {condition} market {index}.",
    }


def _write_acquisition(tmp_path, *, mixed_empty_a: bool = True):
    acquisition = tmp_path / "acquisition"
    rows_root = acquisition / "rows"
    records: list[dict[str, object]] = []
    timestamp = datetime(2026, 9, 19, 8, 30, tzinfo=UTC).isoformat().replace("+00:00", "Z")

    for index in range(12):
        market_id = str(4000 + index)
        event_id = str(5000 + index)
        ready = index < 10
        a_empty = mixed_empty_a and index < 2 and ready
        record: dict[str, object] = {
            "market_id": market_id,
            "event_id": event_id,
            "question_id": f"polymarket-market:{market_id}",
            "status": "forecast_ready" if ready else "market_binding_failure",
            "forecast_ready": ready,
        }
        if ready:
            record["condition_a_status"] = "verified_empty" if a_empty else "verified_complete"
            record["condition_b_status"] = "verified_complete"
        records.append(record)
        if not ready:
            continue

        row_directory = rows_root / session.v01._safe_market_id(market_id)
        row = {
            "market_id": market_id,
            "event_id": event_id,
            "within_event_rank": 1,
            "question_text": f"Will test event {index} happen?",
            "description": "Resolves Yes if the specified test event happens.",
            "scheduled_end_at": "2026-10-10T00:00:00Z",
            "market_probability": 0.5,
            "market_price_timestamp": timestamp,
            "source_cutoff_at": timestamp,
        }
        a_items = [] if a_empty else [_evidence_item(index, "a", timestamp)]
        b_items = [_evidence_item(index, "b", timestamp)]
        packet_a = session._packet(
            question_id=f"polymarket-market:{market_id}",
            status="verified_empty" if a_empty else "verified_complete",
            raw_items=a_items,
            capture_completed_at=timestamp,
            market_price_timestamp=timestamp,
            condition="Condition A",
        )
        packet_b = session._packet(
            question_id=f"polymarket-market:{market_id}",
            status="verified_complete",
            raw_items=b_items,
            capture_completed_at=timestamp,
            market_price_timestamp=timestamp,
            condition="Condition B",
        )
        session._atomic_json(row_directory / "bound-row.json", row)
        session._atomic_json(row_directory / "condition-a-packet.json", packet_a.to_dict())
        session._atomic_json(row_directory / "condition-b-packet.json", packet_b.to_dict())

    summary = {
        "schema_version": 1,
        "experiment_id": session.EXPERIMENT_ID,
        "protocol_commit": session.PROTOCOL_COMMIT,
        "preselection_model_manifest_sha256": session.MODEL_MANIFEST_SHA256,
        "forecast_ready_rows": 10,
        "records": records,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    acquisition.mkdir(parents=True, exist_ok=True)
    session._atomic_json(acquisition / "acquisition-summary.json", summary)
    return acquisition


def _mock_model_verification(monkeypatch) -> None:
    monkeypatch.setattr(
        session,
        "verify_model_set",
        lambda **_: {
            "verified": True,
            "models": [
                {"tag": tag, "digest": digest} for tag, digest in session.FROZEN_MODELS
            ],
        },
    )


def test_same_question_runs_independently_under_a_and_b(tmp_path, monkeypatch) -> None:
    acquisition = _write_acquisition(tmp_path)
    _StatefulFakeAdapter.instances = []
    monkeypatch.setattr(session, "OllamaMarketResidualV2Adapter", _StatefulFakeAdapter)
    _mock_model_verification(monkeypatch)

    result = session.run_forecasting(
        acquisition_directory=acquisition,
        output_directory=tmp_path / "forecast",
        code_commit="test-commit",
    )

    assert result["terminal_safety_success"] is True
    assert result["paired_inference_success"] is True
    assert result["adapter_state_isolation"] == "per-model-per-condition"
    assert len(_StatefulFakeAdapter.instances) == 6

    cells = result["cells"]
    assert isinstance(cells, dict)
    assert len(cells) == 6
    for key, value in cells.items():
        expected = 8 if key.endswith("|condition-a") else 10
        assert value["expected_model_calls"] == expected
        assert value["successful_model_calls"] == expected
        assert value["model_failure_noops"] == 0
        assert value["terminal_safety_success"] is True
        assert value["paired_inference_success"] is True

    decision_counts = sorted(len(adapter.decisions) for adapter in _StatefulFakeAdapter.instances)
    assert decision_counts == [8, 8, 8, 10, 10, 10]

    records = result["records"]
    assert isinstance(records, list)
    assert len(records) == 72
    assert sum(record["status"] == "acquisition_failure_no_forecast" for record in records) == 12

    with pytest.raises(session.SourceRoutingSessionError, match="Refusing to replace"):
        session.run_forecasting(
            acquisition_directory=acquisition,
            output_directory=tmp_path / "forecast",
            code_commit="test-commit",
        )


def test_model_failure_is_safe_but_fails_paired_inference_metric(
    tmp_path, monkeypatch
) -> None:
    acquisition = _write_acquisition(tmp_path, mixed_empty_a=False)
    _StatefulFakeAdapter.instances = []

    class _OneFailureAdapter(_StatefulFakeAdapter):
        creation_count = 0

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            type(self).creation_count += 1
            if type(self).creation_count == 2:
                self.fail_next = True

    _OneFailureAdapter.instances = []
    _OneFailureAdapter.creation_count = 0
    monkeypatch.setattr(session, "OllamaMarketResidualV2Adapter", _OneFailureAdapter)
    _mock_model_verification(monkeypatch)

    result = session.run_forecasting(
        acquisition_directory=acquisition,
        output_directory=tmp_path / "forecast-failure",
        code_commit="test-commit",
    )

    assert result["terminal_safety_success"] is True
    assert result["paired_inference_success"] is False
    cells = result["cells"]
    assert isinstance(cells, dict)
    failed_cells = [
        value for value in cells.values() if value["model_failure_noops"] == 1
    ]
    assert len(failed_cells) == 1
    assert failed_cells[0]["terminal_safety_success"] is True
    assert failed_cells[0]["paired_inference_success"] is False
