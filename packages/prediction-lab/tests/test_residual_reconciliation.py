from __future__ import annotations

import copy
import hashlib
import json
import math

import httpx
import pandas as pd
import pytest
from test_residual_adapter import _metadata

from prediction_lab.cases import attach_model_probabilities
from prediction_lab.datasets import freeze_cases
from prediction_lab.evaluation import evaluate_forecasts
from prediction_lab.research_cache import FilesystemForecastCache, write_immutable_json
from prediction_lab.research_forecaster import build_model_request, forecast_question
from prediction_lab.research_types import (
    EvidenceAvailability,
    EvidenceItem,
    EvidencePacket,
    ForecastArtifact,
    ResearchContractError,
    content_hash,
)
from prediction_lab.residual_reconciliation import reconcile_records, reconcile_run
from prediction_lab.residual_v2 import PROMPT_VERSION, OllamaMarketResidualV2Adapter


def synthetic(
    tmp_path,
    action="increase",
    strength="weak",
    market=0.3,
    empty=False,
    legacy=False,
    duplicate=False,
    question_id="q",
):
    packet = EvidencePacket.create(
        question_id=question_id,
        forecasted_at="2025-02-01T00:00:00Z",
        research_cutoff_at="2025-02-01T00:00:00Z",
        evidence_items=[]
        if empty
        else [
            EvidenceItem.create(
                source_id="s",
                source_type="test",
                uri_or_reference="test://x",
                title="Test",
                available_at="2025-01-01T00:00:00Z",
                retrieved_at="2026-01-01T00:00:00Z",
                text="Synthetic evidence",
            )
        ],
        availability=None
        if legacy
        else EvidenceAvailability(
            "verified_empty" if empty else "verified_complete", "Synthetic acquisition"
        ),
    )
    raw = {
        "action": action,
        "evidence_strength": strength,
        "confidence_or_uncertainty": " uncertain ",
        "critique": " limited ",
        "cited_source_ids": ["s", "s"] if duplicate else ["s"],
    }
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        assert not empty
        return httpx.Response(200, json={"message": {"content": json.dumps(raw)}})

    from prediction_lab.residual_adapter import OllamaMarketResidualAdapter

    cls = OllamaMarketResidualAdapter if legacy else OllamaMarketResidualV2Adapter
    adapter = cls(
        model="llama3.1:8b",
        metadata=_metadata(),
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    config = {
        "mode": "market-aware",
        "dataset_role": "development-only",
        "experiment_id": "synthetic",
        "prompt_version": "market-residual-v1" if legacy else PROMPT_VERSION,
    }
    case = {
        "question_id": question_id,
        "question_text": "Test?",
        "event_id": "e",
        "forecasted_at": "2025-02-01T00:00:00Z",
        "source_cutoff_at": "2025-02-01T00:00:00Z",
        "market_price_timestamp": "2025-02-01T00:00:00Z",
        "resolved_at": "2025-02-08T00:00:00Z",
        "market_probability": market,
        "outcome": 1,
        "split": "development",
    }
    csv, manifest = tmp_path / "development.csv", tmp_path / "manifest.json"
    freeze_cases(
        pd.DataFrame([case]),
        csv_path=csv,
        manifest_path=manifest,
        source_name="synthetic",
        source_revision="test",
        selection_policy="test",
    )
    digest = hashlib.sha256(csv.read_bytes()).hexdigest()
    kwargs = {
        "experiment_id": "synthetic",
        "benchmark_hash": digest,
        "code_commit": "test",
        "experiment_config_hash": content_hash(config),
        "question_id": question_id,
        "question_text": "Test?",
        "evidence_packet": packet,
        "prompt_version": config["prompt_version"],
        "mode": "market-aware",
        "market_probability": market,
        "adapter": adapter,
        "cache": FilesystemForecastCache(tmp_path / "cache"),
    }
    artifact, hit = forecast_question(**kwargs)
    assert not hit
    decisions = adapter.decision_records()
    adapter._decision_records.clear()
    cached, hit = forecast_question(**kwargs)
    assert hit and cached == artifact
    assert cached.residual_decision == (None if legacy else decisions[question_id])
    return (
        {"cases": [case], "artifacts": [artifact], "packets": [packet], "decisions": decisions},
        config,
        requests,
    )


@pytest.mark.parametrize(
    "action,strength,delta",
    [
        ("increase", "weak", 0.25),
        ("increase", "moderate", 0.5),
        ("increase", "strong", 0.75),
        ("decrease", "weak", -0.25),
        ("decrease", "moderate", -0.5),
        ("decrease", "strong", -0.75),
        ("abstain", "none", 0),
    ],
)
def test_independent_mapping_scores_counts_and_cache(tmp_path, action, strength, delta):
    data, _, requests = synthetic(tmp_path, action, strength, duplicate=True)
    result = reconcile_records(**data)
    p = 1 / (1 + math.exp(-(math.log(0.3 / 0.7) + delta))) if delta else 0.3
    row = result["rows"][0]
    assert row["final_probability"] == pytest.approx(p, abs=1e-15)
    assert row["model_brier"] == pytest.approx((p - 1) ** 2)
    assert row["model_log_loss"] == pytest.approx(-math.log(p))
    assert row["market_brier"] == pytest.approx(0.49)
    assert row["market_log_loss"] == pytest.approx(-math.log(0.3))
    assert result["aggregate"]["model_brier"] == row["model_brier"]
    assert result["slices"]["zero_evidence"]["model_brier"] is None
    assert result["action_counts"][action] == result["strength_counts"][strength] == 1
    assert len(requests) == 1
    user_request = json.loads(requests[0]["messages"][1]["content"])
    assert set(user_request["instructions"]["output_fields"]) == {
        "action",
        "evidence_strength",
        "confidence_or_uncertainty",
        "critique",
        "cited_source_ids",
    }


@pytest.mark.parametrize("market", [0.0, 0.37, 1.0])
def test_verified_empty_exact_noop_and_boundary_losses(tmp_path, market):
    data, _, requests = synthetic(tmp_path, market=market, empty=True)
    result = reconcile_records(**data)
    assert requests == []
    assert result["rows"][0]["final_probability"] == market
    assert result["aggregate"]["brier_delta"] == 0
    assert math.isfinite(result["aggregate"]["model_log_loss"])
    assert result["action_counts"]["hard_noop"] == 1
    assert result["slices"]["zero_evidence"]["sample_size"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("action", "decrease"),
        ("logit_delta", 0.5),
        ("market_probability", 0.4),
        ("final_probability", 0.9),
        ("hard_noop", True),
        ("cited_source_ids", []),
        ("mapping_version", "other"),
    ],
)
def test_ledger_cannot_diverge_from_bound_artifact(tmp_path, field, value):
    data, _, _ = synthetic(tmp_path)
    data["decisions"]["q"][field] = value
    with pytest.raises(ResearchContractError, match="immutable forecast decision"):
        reconcile_records(**data)


def test_artifact_binding_is_immutable_and_hashed(tmp_path):
    data, _, _ = synthetic(tmp_path)
    artifact = data["artifacts"][0]
    detached = artifact.residual_decision
    detached["action"] = "decrease"
    assert artifact.residual_decision["action"] == "increase"
    payload = artifact.to_dict()
    payload["residual_decision"]["logit_delta"] = 0.5
    with pytest.raises(ResearchContractError, match="hash mismatch"):
        ForecastArtifact.from_dict(payload)


@pytest.mark.parametrize("tamper", ["missing", "duplicate", "packet", "time", "prior", "outcome"])
def test_reconciliation_rejects_context_tampering(tmp_path, tamper):
    data, _, _ = synthetic(tmp_path)
    if tamper == "missing":
        data["decisions"] = {}
    elif tamper == "duplicate":
        data["artifacts"] *= 2
    elif tamper == "packet":
        data["packets"] = [
            EvidencePacket.create(
                question_id="q",
                forecasted_at="2025-02-01T00:00:00Z",
                research_cutoff_at="2025-02-01T00:00:00Z",
                evidence_items=[],
            )
        ]
    elif tamper == "time":
        data["cases"][0]["forecasted_at"] = "2025-02-02T00:00:00Z"
    elif tamper == "prior":
        data["cases"][0]["market_probability"] = 0.4
    else:
        data["cases"][0]["outcome"] = 2
    with pytest.raises(ResearchContractError):
        reconcile_records(**data)


def test_legacy_explicit_opt_in_does_not_claim_binding(tmp_path):
    data, _, _ = synthetic(tmp_path, legacy=True)
    with pytest.raises(ResearchContractError, match="legacy opt-in"):
        reconcile_records(**data)
    assert reconcile_records(**data, allow_legacy_unbound=True)["legacy_unbound_count"] == 1
    packet = data["packets"][0]
    old = build_model_request(
        question_id="q",
        question_text="Test?",
        evidence_packet=packet,
        prompt_version="market-residual-v1",
        mode="market-aware",
        market_probability=0.3,
    )
    assert "final_probability" in old["instructions"]["output_fields"]


def test_full_offline_report_reconciliation_and_report_tampering(tmp_path):
    data, config, _ = synthetic(tmp_path)
    artifact, packet = data["artifacts"][0], data["packets"][0]
    root = tmp_path / "run"
    write_immutable_json(root / "artifacts" / f"{artifact.artifact_hash}.json", artifact.to_dict())
    write_immutable_json(root / "evidence" / f"{packet.packet_hash}.json", packet.to_dict())
    summary = reconcile_records(**data)["aggregate"]
    report = {
        "artifact_records": [{"question_id": "q", "artifact_hash": artifact.artifact_hash}],
        "benchmark_hash": artifact.benchmark_hash,
        "code_commit": "test",
        "config": config,
        "experiment_config_hash": content_hash(config),
        "model_metadata": _metadata().to_dict(),
        "execution": {
            "total_questions": 1,
            "successful_forecasts": 1,
            "failed_forecasts": 0,
            "forecast_coverage": 1.0,
        },
        "failures": [],
        "evaluation": evaluate_forecasts(
            attach_model_probabilities(
                pd.DataFrame(data["cases"]),
                [artifact.final_probability],
                model_name="synthetic",
            )
        ).to_dict(),
    }

    def check(payload, digest=None):
        path = root / "reports" / f"{content_hash(payload)}.json"
        write_immutable_json(path, payload)
        return reconcile_run(
            development_csv=tmp_path / "development.csv",
            development_manifest=tmp_path / "manifest.json",
            report_path=path,
            expected_development_sha256=digest or artifact.benchmark_hash,
        )

    assert check(report)["aggregate"] == summary
    with pytest.raises(ResearchContractError, match="authorized digest"):
        check(report, "a" * 64)
    for mutate in (
        lambda r: r["evaluation"].update(model_brier=0.01),
        lambda r: r["artifact_records"][0].update(artifact_hash="../escape"),
        lambda r: r.update(code_commit="other"),
        lambda r: r["execution"].update(failed_forecasts=1),
    ):
        tampered = copy.deepcopy(report)
        mutate(tampered)
        with pytest.raises(ResearchContractError):
            check(tampered)


def test_mixed_cohort_aggregates_slices_and_counts(tmp_path):
    a, _, _ = synthetic(tmp_path / "a", question_id="a")
    b, _, _ = synthetic(tmp_path / "b", question_id="b", empty=True, market=0.8)
    b["cases"][0]["outcome"] = 0
    data = {k: a[k] + b[k] for k in ("cases", "artifacts", "packets")}
    data["decisions"] = a["decisions"] | b["decisions"]
    result = reconcile_records(**data)
    rows = result["rows"]
    scored = evaluate_forecasts(
        attach_model_probabilities(
            pd.DataFrame(data["cases"]),
            [a.final_probability for a in data["artifacts"]],
            model_name="synthetic",
        )
    ).to_dict()
    assert result["aggregate"]["sample_size"] == 2
    for metric in ("model_brier", "market_brier", "model_log_loss", "market_log_loss"):
        assert result["aggregate"][metric] == math.fsum(r[metric] for r in rows) / 2
        assert result["aggregate"][metric] == pytest.approx(scored[metric], abs=1e-15)
        assert result["slices"]["evidence_bearing"][metric] == rows[0][metric]
        assert result["slices"]["zero_evidence"][metric] == rows[1][metric]
    assert result["action_counts"] == {"increase": 1, "decrease": 0, "abstain": 0, "hard_noop": 1}
    assert result == reconcile_records(**(data | {"cases": list(reversed(data["cases"]))}))


def test_independent_reconciliation_rejects_consistently_rehashed_bad_mapping(tmp_path):
    data, _, _ = synthetic(tmp_path)
    payload = data["artifacts"][0].to_dict()
    payload["residual_decision"]["logit_delta"] = 0.5
    payload.pop("artifact_hash")
    payload["artifact_hash"] = content_hash(payload)
    data["artifacts"] = [ForecastArtifact.from_dict(payload)]
    data["decisions"] = {"q": data["artifacts"][0].residual_decision}
    with pytest.raises(ResearchContractError, match="fixed mapping"):
        reconcile_records(**data)


def test_v2_rejects_legacy_request_and_unknown_acquisition(tmp_path):
    from test_residual_adapter import _request

    from prediction_lab.residual_adapter import OllamaMarketResidualAdapter

    adapter = OllamaMarketResidualV2Adapter(model="llama3.1:8b", metadata=_metadata())
    with pytest.raises(ResearchContractError, match="requires market-residual-v2"):
        adapter.generate(_request())
    data, _, _ = synthetic(tmp_path, legacy=True)
    packet = data["packets"][0]
    kwargs = {
        "experiment_id": "test",
        "benchmark_hash": "test",
        "code_commit": "test",
        "experiment_config_hash": "test",
        "question_id": "q",
        "question_text": "Test?",
        "evidence_packet": packet,
        "prompt_version": PROMPT_VERSION,
        "mode": "market-aware",
        "market_probability": 0.3,
        "cache": FilesystemForecastCache(tmp_path / "newcache"),
    }
    with pytest.raises(ResearchContractError, match="explicit verified evidence"):
        forecast_question(**kwargs, adapter=adapter)
    with pytest.raises(ResearchContractError, match="versioned adapter"):
        forecast_question(
            **kwargs, adapter=OllamaMarketResidualAdapter(model="llama3.1:8b", metadata=_metadata())
        )
