"""One-shot residual-v2 forecasting for the frozen prospective clustered cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from prediction_lab import prospective_evidence_v01 as evidence_contract
from prediction_lab.research_forecaster import build_model_request
from prediction_lab.research_types import (
    EvidencePacket,
    ModelMetadata,
    ResearchContractError,
    content_hash,
)
from prediction_lab.residual_adapter import RESIDUAL_MAPPING_VERSION
from prediction_lab.residual_v2 import (
    PROMPT_VERSION,
    OllamaMarketResidualV2Adapter,
)

EXPERIMENT_ID = "prospective-clustered-residual-v2-v0.1"
MODEL_TAG = "llama3.1:8b"
MODEL_DIGEST = "sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e"
MODEL_PROVIDER = "Meta via local Ollama"
MODEL_ID = "Meta-Llama-3.1-8B-Instruct"
MODEL_RELEASE_DATE = "2024-07-23T00:00:00Z"
MODEL_KNOWLEDGE_CUTOFF = "2023-12-31T23:59:59Z"
FORECASTER_PROTOCOL_COMMIT = evidence_contract.FORECASTER_PROTOCOL_COMMIT
SCHEMA_CLARIFICATION_COMMIT = evidence_contract.SCHEMA_CLARIFICATION_COMMIT
EVIDENCE_STATUS_CLARIFICATION_COMMIT = (
    evidence_contract.EVIDENCE_STATUS_CLARIFICATION_COMMIT
)
CUSTODY_ROWS = evidence_contract.CUSTODY_ROWS
CUSTODY_EVENT_GROUPS = evidence_contract.CUSTODY_EVENT_GROUPS
CUSTODY_COHORT_SHA256 = evidence_contract.CUSTODY_COHORT_SHA256


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _model_metadata() -> ModelMetadata:
    return ModelMetadata.create(
        provider=MODEL_PROVIDER,
        model_id=MODEL_ID,
        immutable_version=MODEL_DIGEST,
        release_date=MODEL_RELEASE_DATE,
        knowledge_cutoff=MODEL_KNOWLEDGE_CUTOFF,
        execution_mode="local",
        contamination_assessment="historical-safe",
        contamination_notes=(
            "Static Meta Llama 3.1 8B Instruct model with official December 2023 "
            "knowledge cutoff; exact local Ollama artifact digest is frozen by protocol."
        ),
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchContractError(f"Cannot read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ResearchContractError(f"Expected JSON object: {path}")
    return value


def _load_fixture(
    evidence_directory: Path,
    *,
    expected_fixture_sha256: str,
    expected_evidence_code_commit: str,
    expected_packets_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = _load_json(evidence_directory / "evidence-summary.json")
    fixture_path = evidence_directory / "evidence-fixture.json"
    fixture_bytes = fixture_path.read_bytes()
    actual_fixture = _sha256_bytes(fixture_bytes)
    if actual_fixture != expected_fixture_sha256:
        raise ResearchContractError(
            f"Evidence fixture digest changed: {actual_fixture} != {expected_fixture_sha256}"
        )
    if summary.get("evidence_fixture_sha256") != expected_fixture_sha256:
        raise ResearchContractError("Evidence summary fixture digest changed")
    if summary.get("evidence_packets_sha256") != expected_packets_sha256:
        raise ResearchContractError("Evidence packet-set digest changed")
    if summary.get("code_commit") != expected_evidence_code_commit:
        raise ResearchContractError("Evidence acquisition code commit changed")
    if summary.get("forecaster_protocol_commit") != FORECASTER_PROTOCOL_COMMIT:
        raise ResearchContractError("Evidence forecaster protocol identity changed")
    if summary.get("rows") != CUSTODY_ROWS or summary.get("event_groups") != CUSTODY_EVENT_GROUPS:
        raise ResearchContractError("Evidence cohort accounting changed")
    if summary.get("forecast_ready") is not True:
        raise ResearchContractError("Evidence artifact is not forecast-ready")
    if summary.get("reserved_holdout_accessed") is not False:
        raise ResearchContractError("Evidence artifact reports reserved holdout access")
    if summary.get("model_forecast_run") is not False:
        raise ResearchContractError("Evidence artifact unexpectedly reports a model run")
    if summary.get("outcomes_accessed") is not False:
        raise ResearchContractError("Evidence artifact unexpectedly reports outcome access")
    statuses = summary.get("status_counts")
    if not isinstance(statuses, dict) or sum(int(value) for value in statuses.values()) != CUSTODY_ROWS:
        raise ResearchContractError("Evidence status accounting is malformed")
    if not set(statuses).issubset({"verified_complete", "verified_empty"}):
        raise ResearchContractError("Evidence artifact contains nonterminal acquisition states")

    try:
        fixture = json.loads(fixture_bytes)
    except json.JSONDecodeError as exc:
        raise ResearchContractError("Evidence fixture is malformed JSON") from exc
    if not isinstance(fixture, dict):
        raise ResearchContractError("Evidence fixture must be an object")
    questions = fixture.get("questions")
    availability = fixture.get("availability")
    if not isinstance(questions, dict) or not isinstance(availability, dict):
        raise ResearchContractError("Evidence fixture lacks questions/availability mappings")
    if set(questions) != set(availability) or len(questions) != CUSTODY_ROWS:
        raise ResearchContractError("Evidence fixture question identities changed")
    return fixture, summary


def _packets_from_fixture(
    fixture: Mapping[str, Any],
    custody_rows: list[dict[str, Any]],
) -> dict[str, EvidencePacket]:
    questions = fixture["questions"]
    availability = fixture["availability"]
    if not isinstance(questions, dict) or not isinstance(availability, dict):
        raise ResearchContractError("Malformed evidence fixture")
    packets: dict[str, EvidencePacket] = {}
    for row in custody_rows:
        question_id = evidence_contract._question_id(row)
        items = questions.get(question_id)
        state = availability.get(question_id)
        if not isinstance(items, list) or not isinstance(state, dict):
            raise ResearchContractError(f"Evidence missing for {question_id}")
        packet = EvidencePacket.from_dict(
            {
                "schema_version": 2,
                "question_id": question_id,
                "forecasted_at": row["market_price_timestamp"],
                "research_cutoff_at": row["source_cutoff_at"],
                "evidence_items": items,
                "availability": state,
            }
        )
        packet.assert_safe_for_cutoff(row["source_cutoff_at"])
        packets[question_id] = packet
    return packets


def _failure_noop_record(
    *,
    row: Mapping[str, Any],
    packet: EvidencePacket,
    failure: Exception,
) -> dict[str, object]:
    prior = float(row["market_probability"])
    return {
        "question_id": packet.question_id,
        "market_id": str(row["market_id"]),
        "event_id": str(row["event_id"]),
        "within_event_rank": int(row["within_event_rank"]),
        "forecasted_at": str(row["market_price_timestamp"]),
        "research_cutoff_at": str(row["source_cutoff_at"]),
        "market_probability": prior,
        "final_probability": prior,
        "status": "model_failure_noop",
        "action": "model_failure_noop",
        "evidence_strength": "none",
        "hard_noop": True,
        "logit_delta": 0.0,
        "mapping_version": RESIDUAL_MAPPING_VERSION,
        "cited_source_ids": [],
        "confidence_or_uncertainty": "deterministic no-op after single model attempt failed",
        "critique": "Model attempt failed; frozen market prior preserved exactly.",
        "failure_class": type(failure).__name__,
        "failure_message": str(failure)[:1000],
        "evidence_packet_hash": packet.packet_hash,
        "model_called": True,
    }


def _empty_noop_record(
    *,
    row: Mapping[str, Any],
    packet: EvidencePacket,
) -> dict[str, object]:
    prior = float(row["market_probability"])
    return {
        "question_id": packet.question_id,
        "market_id": str(row["market_id"]),
        "event_id": str(row["event_id"]),
        "within_event_rank": int(row["within_event_rank"]),
        "forecasted_at": str(row["market_price_timestamp"]),
        "research_cutoff_at": str(row["source_cutoff_at"]),
        "market_probability": prior,
        "final_probability": prior,
        "status": "verified_empty_noop",
        "action": "hard_noop",
        "evidence_strength": "none",
        "hard_noop": True,
        "logit_delta": 0.0,
        "mapping_version": RESIDUAL_MAPPING_VERSION,
        "cited_source_ids": [],
        "confidence_or_uncertainty": "deterministic no-op: verified empty evidence",
        "critique": "Bounded timestamp-safe acquisition completed with no admitted evidence.",
        "failure_class": None,
        "failure_message": None,
        "evidence_packet_hash": packet.packet_hash,
        "model_called": False,
    }


def forecast_row(
    row: Mapping[str, Any],
    *,
    packet: EvidencePacket,
    adapter: OllamaMarketResidualV2Adapter,
) -> dict[str, object]:
    prior = float(row["market_probability"])
    if not math.isfinite(prior) or not 0.0 < prior < 1.0:
        raise ResearchContractError("Frozen market probability is outside (0, 1)")
    if packet.availability is None:
        raise ResearchContractError("Forecast packet lacks explicit availability state")
    if packet.availability.status == "verified_empty":
        if packet.evidence_items:
            raise ResearchContractError("verified_empty packet unexpectedly contains evidence")
        return _empty_noop_record(row=row, packet=packet)
    if packet.availability.status != "verified_complete":
        raise ResearchContractError(
            f"Forecasting forbidden for evidence state {packet.availability.status!r}"
        )
    if not packet.evidence_items:
        raise ResearchContractError("verified_complete packet contains no evidence")

    problem_text = evidence_contract._canonical_problem_text(row)
    request = build_model_request(
        question_id=packet.question_id,
        question_text=problem_text,
        evidence_packet=packet,
        prompt_version=PROMPT_VERSION,
        mode="market-aware",
        market_probability=prior,
    )
    try:
        output = adapter.generate(request)
        decisions = adapter.decision_records()
        decision = decisions.get(packet.question_id)
        if decision is None:
            raise ResearchContractError("Residual adapter did not bind a decision record")
        final_probability = output.get("final_probability")
        if isinstance(final_probability, bool) or not isinstance(final_probability, (int, float)):
            raise ResearchContractError("Residual adapter returned invalid final probability")
        final = float(final_probability)
        if decision.get("final_probability") != final:
            raise ResearchContractError("Residual decision diverges from forecast output")
        citations = output.get("cited_source_ids")
        if not isinstance(citations, list) or not all(isinstance(value, str) for value in citations):
            raise ResearchContractError("Residual adapter returned invalid citations")
        return {
            "question_id": packet.question_id,
            "market_id": str(row["market_id"]),
            "event_id": str(row["event_id"]),
            "within_event_rank": int(row["within_event_rank"]),
            "forecasted_at": str(row["market_price_timestamp"]),
            "research_cutoff_at": str(row["source_cutoff_at"]),
            "market_probability": prior,
            "final_probability": final,
            "status": "model_evaluated",
            "action": decision["action"],
            "evidence_strength": decision["evidence_strength"],
            "hard_noop": bool(decision["hard_noop"]),
            "logit_delta": float(decision["logit_delta"]),
            "mapping_version": decision["mapping_version"],
            "cited_source_ids": citations,
            "confidence_or_uncertainty": str(output["confidence_or_uncertainty"]),
            "critique": str(output["critique"]),
            "failure_class": None,
            "failure_message": None,
            "evidence_packet_hash": packet.packet_hash,
            "model_called": True,
        }
    except ResearchContractError as exc:
        return _failure_noop_record(row=row, packet=packet, failure=exc)


def run_forecasts(
    *,
    custody_zip: Path,
    evidence_directory: Path,
    output_directory: Path,
    code_commit: str,
    expected_fixture_sha256: str,
    expected_packets_sha256: str,
    expected_evidence_code_commit: str,
    adapter: OllamaMarketResidualV2Adapter,
) -> dict[str, object]:
    rows, _ = evidence_contract.load_verified_custody_archive(custody_zip)
    fixture, evidence_summary = _load_fixture(
        evidence_directory,
        expected_fixture_sha256=expected_fixture_sha256,
        expected_evidence_code_commit=expected_evidence_code_commit,
        expected_packets_sha256=expected_packets_sha256,
    )
    packets = _packets_from_fixture(fixture, rows)
    adapter.metadata.assert_safe_for_historical_scoring(rows[0]["market_price_timestamp"])

    if output_directory.exists():
        raise ResearchContractError("Refusing to replace existing forecast output")
    output_directory.mkdir(parents=True)

    forecasts: list[dict[str, object]] = []
    for row in rows:
        question_id = evidence_contract._question_id(row)
        packet = packets[question_id]
        forecasts.append(forecast_row(row, packet=packet, adapter=adapter))

    if len(forecasts) != CUSTODY_ROWS:
        raise ResearchContractError("Forecast denominator changed")
    question_ids = [str(row["question_id"]) for row in forecasts]
    if len(set(question_ids)) != CUSTODY_ROWS:
        raise ResearchContractError("Forecast question IDs are not unique")
    if set(question_ids) != set(packets):
        raise ResearchContractError("Forecast question set differs from evidence set")

    status_counts = Counter(str(row["status"]) for row in forecasts)
    action_counts = Counter(str(row["action"]) for row in forecasts)
    strength_counts = Counter(str(row["evidence_strength"]) for row in forecasts)
    model_calls = sum(bool(row["model_called"]) for row in forecasts)
    model_failures = status_counts["model_failure_noop"]
    empty_noops = status_counts["verified_empty_noop"]
    model_evaluated = status_counts["model_evaluated"]
    if model_calls != model_evaluated + model_failures:
        raise ResearchContractError("Model-call accounting is inconsistent")

    forecasts_path = output_directory / "forecasts.jsonl"
    payload = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        for row in forecasts
    )
    forecasts_path.write_bytes(payload)

    model_metadata = adapter.metadata.to_dict()
    config = {
        "experiment_id": EXPERIMENT_ID,
        "prompt_version": PROMPT_VERSION,
        "residual_mapping_version": RESIDUAL_MAPPING_VERSION,
        "model_tag": MODEL_TAG,
        "model_metadata": model_metadata,
        "forecaster_protocol_commit": FORECASTER_PROTOCOL_COMMIT,
        "schema_clarification_commit": SCHEMA_CLARIFICATION_COMMIT,
        "evidence_status_clarification_commit": EVIDENCE_STATUS_CLARIFICATION_COMMIT,
        "custody_cohort_sha256": CUSTODY_COHORT_SHA256,
        "evidence_fixture_sha256": expected_fixture_sha256,
        "evidence_packets_sha256": expected_packets_sha256,
        "evidence_code_commit": expected_evidence_code_commit,
        "code_commit": code_commit,
        "failure_policy": "single-attempt-model-failure-noop",
        "zero_evidence_policy": "verified-empty-market-noop",
    }
    config_hash = content_hash(config)
    _atomic_json(output_directory / "forecast-config.json", {**config, "config_hash": config_hash})

    summary: dict[str, object] = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "code_commit": code_commit,
        "forecaster_protocol_commit": FORECASTER_PROTOCOL_COMMIT,
        "prompt_version": PROMPT_VERSION,
        "residual_mapping_version": RESIDUAL_MAPPING_VERSION,
        "model_tag": MODEL_TAG,
        "model_digest": MODEL_DIGEST,
        "rows": CUSTODY_ROWS,
        "event_groups": CUSTODY_EVENT_GROUPS,
        "status_counts": dict(sorted(status_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "evidence_strength_counts": dict(sorted(strength_counts.items())),
        "model_calls": model_calls,
        "model_evaluated": model_evaluated,
        "model_failure_noops": model_failures,
        "verified_empty_noops": empty_noops,
        "forecast_config_hash": config_hash,
        "forecasts_sha256": _sha256_bytes(payload),
        "evidence_fixture_sha256": expected_fixture_sha256,
        "evidence_packets_sha256": expected_packets_sha256,
        "evidence_code_commit": expected_evidence_code_commit,
        "evidence_status_counts": evidence_summary["status_counts"],
        "reserved_holdout_accessed": False,
        "outcomes_accessed": False,
        "scoring_run": False,
        "confirmatory_edge_claim_authorized": False,
    }
    _atomic_json(output_directory / "forecast-summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("custody_zip", type=Path)
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--expected-evidence-fixture-sha256", required=True)
    parser.add_argument("--expected-evidence-packets-sha256", required=True)
    parser.add_argument("--expected-evidence-code-commit", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    adapter = OllamaMarketResidualV2Adapter(
        model=MODEL_TAG,
        metadata=_model_metadata(),
        base_url=args.base_url,
        timeout_seconds=180.0,
    )
    try:
        summary = run_forecasts(
            custody_zip=args.custody_zip,
            evidence_directory=args.evidence_directory,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
            expected_fixture_sha256=args.expected_evidence_fixture_sha256,
            expected_packets_sha256=args.expected_evidence_packets_sha256,
            expected_evidence_code_commit=args.expected_evidence_code_commit,
            adapter=adapter,
        )
    finally:
        adapter.close()

    safe = {
        key: summary[key]
        for key in (
            "experiment_id",
            "rows",
            "event_groups",
            "status_counts",
            "action_counts",
            "evidence_strength_counts",
            "model_calls",
            "model_evaluated",
            "model_failure_noops",
            "verified_empty_noops",
            "forecast_config_hash",
            "forecasts_sha256",
            "reserved_holdout_accessed",
            "outcomes_accessed",
            "scoring_run",
            "confirmatory_edge_claim_authorized",
        )
    }
    print(json.dumps(safe, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
