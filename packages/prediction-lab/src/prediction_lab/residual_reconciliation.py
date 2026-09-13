"""Offline independent arithmetic and provenance audit. Never generates forecasts.

The scalar formulas intentionally do not call the production residual mapper or
evaluator. Legacy unbound ledgers require explicit opt-in and remain labelled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from prediction_lab.datasets import verify_frozen_dataset
from prediction_lab.research_types import (
    EvidencePacket,
    ForecastArtifact,
    ResearchContractError,
    content_hash,
    parse_utc,
)

_HASH = re.compile(r"^[0-9a-f]{64}$")
_MAGNITUDES = {"weak": 0.25, "moderate": 0.50, "strong": 0.75}
_EPSILON = 1e-15  # Existing evaluator's log-loss convention, not probability clipping.


def _number(value: object, label: str, *, probability: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchContractError(f"Non-numeric {label}")
    result = float(value)
    if not math.isfinite(result) or (probability and not 0 <= result <= 1):
        raise ResearchContractError(f"Invalid {label}")
    return result


def _equal(actual: object, expected: float, label: str) -> None:
    if not math.isclose(_number(actual, label), expected, rel_tol=0, abs_tol=1e-15):
        raise ResearchContractError(f"Reconciliation mismatch: {label}")


def _log_loss(probability: float, outcome: int) -> float:
    bounded = min(1 - _EPSILON, max(_EPSILON, probability))
    return -math.log(bounded if outcome else 1 - bounded)


def _aggregate(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "model_brier",
        "market_brier",
        "brier_delta",
        "model_log_loss",
        "market_log_loss",
        "log_loss_delta",
    )
    return {
        "sample_size": len(rows),
        **{
            field: math.fsum(row[field] for row in rows) / len(rows) if rows else None
            for field in fields
        },
    }


def reconcile_records(
    *,
    cases: Sequence[Mapping[str, Any]],
    artifacts: Sequence[ForecastArtifact],
    packets: Sequence[EvidencePacket],
    decisions: Mapping[str, Mapping[str, object]],
    allow_legacy_unbound: bool = False,
) -> dict[str, Any]:
    def indexed(values: Sequence[Any], key: Any) -> dict[str, Any]:
        result = {str(key(value)): value for value in values}
        if len(result) != len(values):
            raise ResearchContractError("Duplicate reconciliation question IDs")
        return result

    case_by_id = indexed(cases, lambda row: row["question_id"])
    artifact_by_id = indexed(artifacts, lambda artifact: artifact.question_id)
    packet_by_id = indexed(packets, lambda packet: packet.question_id)
    if not cases or not (
        set(case_by_id) == set(artifact_by_id) == set(packet_by_id) == set(decisions)
    ):
        raise ResearchContractError("Reconciliation requires identical complete question sets")
    rows: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    strength_counts: Counter[str] = Counter()
    for question_id in sorted(case_by_id):
        case = case_by_id[question_id]
        artifact = artifact_by_id[question_id]
        packet = packet_by_id[question_id]
        decision = decisions[question_id]
        if not isinstance(decision, Mapping):
            raise ResearchContractError("Malformed residual decision record")
        # Roundtrip integrity checks also cover mutated in-memory objects.
        ForecastArtifact.from_dict(artifact.to_dict())
        EvidencePacket.from_dict(packet.to_dict())
        if case.get("split") != "development":
            raise ResearchContractError("Reconciliation accepts development cases only")
        if artifact.blind_or_market_aware != "market-aware":
            raise ResearchContractError("Residual reconciliation requires market-aware forecasts")
        if artifact.evidence_packet_hash != packet.packet_hash:
            raise ResearchContractError("Forecast/evidence packet binding mismatch")
        forecast_time = parse_utc(case["forecasted_at"], field="forecasted_at")
        cutoff = parse_utc(case["source_cutoff_at"], field="source_cutoff_at")
        if artifact.forecasted_at != forecast_time or packet.forecasted_at != forecast_time:
            raise ResearchContractError("Forecast timestamp mismatch")
        if packet.research_cutoff_at != cutoff:
            raise ResearchContractError("Evidence cutoff mismatch")
        if parse_utc(case["market_price_timestamp"], field="price time") > forecast_time:
            raise ResearchContractError("Future market price")
        if parse_utc(case["resolved_at"], field="resolution") <= forecast_time:
            raise ResearchContractError("Forecast at or after resolution")
        artifact.model_metadata.assert_safe_for_historical_scoring(forecast_time)
        packet.assert_safe_for_cutoff(cutoff)
        if artifact.prompt_version not in {"market-residual-v1", "market-residual-v2"}:
            raise ResearchContractError("Unsupported residual prompt version")
        bound = artifact.residual_decision
        if bound is None:
            if not allow_legacy_unbound or artifact.prompt_version != "market-residual-v1":
                raise ResearchContractError(
                    "Unbound residual provenance requires explicit legacy opt-in"
                )
        elif bound != dict(decision):
            raise ResearchContractError("Residual ledger differs from immutable forecast decision")
        if packet.availability is not None:
            packet.availability.assert_usable()
        elif artifact.prompt_version == "market-residual-v2":
            raise ResearchContractError("Residual-v2 requires explicit evidence acquisition state")
        expected_fields = {
            "action",
            "cited_source_ids",
            "evidence_strength",
            "final_probability",
            "hard_noop",
            "logit_delta",
            "mapping_version",
            "market_probability",
            "raw_model_output",
        }
        if set(decision) != expected_fields or decision["mapping_version"] != "logit-residual-v1":
            raise ResearchContractError("Unknown residual decision contract/mapping")
        market = _number(case["market_probability"], "market", probability=True)
        if (
            _number(decision["market_probability"], "decision market", probability=True) != market
            or artifact.base_rate_probability != market
        ):
            raise ResearchContractError("Residual prior differs from frozen case market")
        citations = decision["cited_source_ids"]
        allowed = {item.source_id for item in packet.evidence_items}
        if (
            not isinstance(citations, list)
            or not all(isinstance(item, str) for item in citations)
            or len(citations) != len(set(citations))
            or not set(citations).issubset(allowed)
            or citations != list(artifact.cited_source_ids)
        ):
            raise ResearchContractError("Residual citation mismatch")
        action, strength = decision["action"], decision["evidence_strength"]
        if not isinstance(action, str) or not isinstance(strength, str):
            raise ResearchContractError("Invalid residual action/strength")
        hard_noop = decision["hard_noop"]
        if not isinstance(hard_noop, bool) or hard_noop != (len(allowed) == 0):
            raise ResearchContractError("Hard no-op does not match actual evidence count")
        raw = decision["raw_model_output"]
        if hard_noop:
            if action != "hard_noop" or strength != "none" or raw is not None or citations:
                raise ResearchContractError("Malformed zero-evidence hard no-op")
            delta = 0.0
        else:
            if not isinstance(raw, dict) or set(raw) != {
                "action",
                "evidence_strength",
                "confidence_or_uncertainty",
                "critique",
                "cited_source_ids",
            }:
                raise ResearchContractError("Missing/malformed raw residual model output")
            if (
                raw["action"] != action
                or raw["evidence_strength"] != strength
                or not isinstance(raw["cited_source_ids"], list)
                or not all(isinstance(x, str) for x in raw["cited_source_ids"])
                or list(dict.fromkeys(raw["cited_source_ids"])) != citations
                or not isinstance(raw["critique"], str)
                or not isinstance(raw["confidence_or_uncertainty"], str)
                or raw["critique"].strip() != artifact.critique
                or raw["confidence_or_uncertainty"].strip() != artifact.confidence_or_uncertainty
            ):
                raise ResearchContractError("Raw residual decision disagrees with scored artifact")
            if action == "abstain" and strength == "none":
                delta = 0.0
            elif action in {"increase", "decrease"} and strength in _MAGNITUDES:
                delta = _MAGNITUDES[strength] * (1 if action == "increase" else -1)
            else:
                raise ResearchContractError("Invalid residual action/strength combination")
        if _number(decision["logit_delta"], "delta") != delta:
            raise ResearchContractError("Residual delta disagrees with fixed mapping")
        if market in (0, 1) or delta == 0:
            final = market
            if decision["final_probability"] != market or artifact.final_probability != market:
                raise ResearchContractError("No-op or boundary probability is not exact")
        else:
            final = 1 / (1 + math.exp(-(math.log(market / (1 - market)) + delta)))
        _equal(decision["final_probability"], final, "decision final probability")
        _equal(artifact.final_probability, final, "artifact final probability")
        _equal(artifact.updated_probability, final, "artifact updated probability")
        outcome = case["outcome"]
        if isinstance(outcome, bool) or outcome not in (0, 1):
            raise ResearchContractError("Outcome must be binary")
        y = int(outcome)
        model_brier, market_brier = (final - y) ** 2, (market - y) ** 2
        model_log, market_log = _log_loss(final, y), _log_loss(market, y)
        action_counts[action] += 1
        strength_counts[strength] += 1
        rows.append(
            {
                "question_id": question_id,
                "artifact_hash": artifact.artifact_hash,
                "evidence_packet_hash": packet.packet_hash,
                "binding": "bound" if bound is not None else "legacy_unbound",
                "evidence_state": packet.availability.status
                if packet.availability
                else "legacy_unspecified",
                "evidence_bearing": bool(allowed),
                "action": action,
                "strength": strength,
                "logit_delta": delta,
                "market_probability": market,
                "final_probability": final,
                "probability_movement": final - market,
                "model_brier": model_brier,
                "market_brier": market_brier,
                "brier_delta": model_brier - market_brier,
                "model_log_loss": model_log,
                "market_log_loss": market_log,
                "log_loss_delta": model_log - market_log,
            }
        )
    return {
        "schema_version": 1,
        "reconciliation_version": "residual-reconciliation-v1",
        "rows": rows,
        "aggregate": _aggregate(rows),
        "slices": {
            label: _aggregate([row for row in rows if row["evidence_bearing"] == flag])
            for label, flag in (("evidence_bearing", True), ("zero_evidence", False))
        },
        "action_counts": {
            key: action_counts[key] for key in ("increase", "decrease", "abstain", "hard_noop")
        },
        "strength_counts": {
            key: strength_counts[key] for key in ("none", "weak", "moderate", "strong")
        },
        "legacy_unbound_count": sum(row["binding"] == "legacy_unbound" for row in rows),
    }


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ResearchContractError("Expected JSON object")
    return value


def _hash_path(root: Path, digest: object) -> Path:
    if not isinstance(digest, str) or not _HASH.fullmatch(digest):
        raise ResearchContractError("Invalid content-addressed artifact identity")
    return root / f"{digest}.json"


def reconcile_run(
    *,
    development_csv: Path,
    development_manifest: Path,
    expected_development_sha256: str,
    report_path: Path,
    decisions_path: Path | None = None,
    allow_legacy_unbound: bool = False,
) -> dict[str, Any]:
    """Read only explicitly supplied development inputs and report-referenced artifact files."""
    if not _HASH.fullmatch(expected_development_sha256):
        raise ResearchContractError("An independently supplied development SHA256 is required")
    if hashlib.sha256(development_csv.read_bytes()).hexdigest() != expected_development_sha256:
        raise ResearchContractError("Development input does not match authorized digest")
    cases = verify_frozen_dataset(csv_path=development_csv, manifest_path=development_manifest)
    if set(cases["split"].astype(str)) != {"development"}:
        raise ResearchContractError("Reconciliation accepts development only")
    report = _json(report_path)
    if content_hash(report) != report_path.stem:
        raise ResearchContractError("Experiment report content hash mismatch")
    if report.get("benchmark_hash") != expected_development_sha256:
        raise ResearchContractError("Report benchmark identity mismatch")
    if (
        report.get("execution")
        != {
            "total_questions": len(cases),
            "successful_forecasts": len(cases),
            "failed_forecasts": 0,
            "forecast_coverage": 1.0,
        }
        or report.get("failures") != []
    ):
        raise ResearchContractError("Complete coverage is required for reconciliation")
    config = report.get("config")
    if not isinstance(config, dict) or content_hash(config) != report.get("experiment_config_hash"):
        raise ResearchContractError("Experiment configuration hash mismatch")
    if config.get("mode") != "market-aware" or config.get("dataset_role") != "development-only":
        raise ResearchContractError("Unexpected experiment role or mode")
    artifacts, packets = [], []
    decisions: dict[str, Mapping[str, object]] = {}
    run_root = report_path.parent.parent
    records = report.get("artifact_records")
    if not isinstance(records, list):
        raise ResearchContractError("Missing forecast artifact records")
    for record in records:
        if not isinstance(record, dict):
            raise ResearchContractError("Malformed forecast artifact record")
        path = _hash_path(run_root / "artifacts", record.get("artifact_hash"))
        artifact = ForecastArtifact.from_dict(_json(path))
        if artifact.artifact_hash != path.stem or artifact.question_id != record.get("question_id"):
            raise ResearchContractError("Report/forecast artifact identity mismatch")
        if record.get("cache_key", artifact.cache_key) != artifact.cache_key:
            raise ResearchContractError("Report/forecast cache identity mismatch")
        if (
            artifact.benchmark_hash != expected_development_sha256
            or artifact.code_commit != report.get("code_commit")
            or artifact.experiment_config_hash != report.get("experiment_config_hash")
            or artifact.experiment_id != config.get("experiment_id")
            or artifact.prompt_version != config.get("prompt_version")
            or artifact.model_metadata.to_dict() != report.get("model_metadata")
        ):
            raise ResearchContractError("Forecast experiment lineage mismatch")
        packet = EvidencePacket.from_dict(
            _json(
                _hash_path(run_root / "evidence", artifact.evidence_packet_hash),
            )
        )
        artifacts.append(artifact)
        packets.append(packet)
        if artifact.residual_decision is not None:
            decisions[artifact.question_id] = artifact.residual_decision
    if decisions_path is not None:
        decisions = _json(decisions_path)
    result = reconcile_records(
        cases=[{str(k): v for k, v in row.items()} for row in cases.to_dict("records")],
        artifacts=artifacts,
        packets=packets,
        decisions=decisions,
        allow_legacy_unbound=allow_legacy_unbound,
    )
    evaluation = report.get("evaluation")
    if not isinstance(evaluation, dict) or evaluation.get("sample_size") != len(cases):
        raise ResearchContractError("Evaluation sample size mismatch")
    for key in ("model_brier", "market_brier", "brier_delta", "model_log_loss", "market_log_loss"):
        _equal(evaluation.get(key), result["aggregate"][key], f"report {key}")
    result["source_report_hash"] = report_path.stem
    result["development_sha256"] = expected_development_sha256
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline development residual reconciliation")
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-development-sha256", required=True)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--allow-legacy-unbound", action="store_true")
    args = parser.parse_args()
    result = reconcile_run(
        development_csv=args.development_csv,
        development_manifest=args.development_manifest,
        expected_development_sha256=args.expected_development_sha256,
        report_path=args.report,
        decisions_path=args.decisions,
        allow_legacy_unbound=args.allow_legacy_unbound,
    )
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
