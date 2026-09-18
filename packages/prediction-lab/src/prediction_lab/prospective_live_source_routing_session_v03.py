"""Paired acquisition and multimodel forecasting for prospective source routing v0.3."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import httpx

from prediction_lab import prospective_forecast_v01 as forecaster
from prediction_lab import prospective_live_rss_v01 as live_rss
from prediction_lab import prospective_live_session_v01 as v01
from prediction_lab import prospective_live_source_routing_v03 as selector
from prediction_lab import prospective_polymarket_custody as custody
from prediction_lab import prospective_source_routing_v03 as routing
from prediction_lab.research_types import EvidenceAvailability, EvidenceItem, EvidencePacket
from prediction_lab.residual_v2 import OllamaMarketResidualV2Adapter

EXPERIMENT_ID = selector.PURPOSE
PROTOCOL_COMMIT = selector.PROTOCOL_COMMIT
MODEL_MANIFEST_SHA256 = selector.MODEL_MANIFEST_SHA256
FROZEN_MODELS = selector.FROZEN_MODELS
TARGET_ROWS = selector.TARGET_COHORT
ACQUISITION_SUCCESS_FLOOR = 10
SELECTION_TO_ACQUISITION_SECONDS = 120 * 60
OLLAMA_TIMEOUT_SECONDS = 1200.0
CONDITIONS = ("condition-a", "condition-b")
TERMINAL_STATUSES = {"model_evaluated", "model_failure_noop", "verified_empty_noop"}


class SourceRoutingSessionError(RuntimeError):
    """Raised when the frozen v0.3 execution contract cannot be satisfied."""


@dataclass(frozen=True)
class _AdapterMetadata:
    immutable_version: str
    execution_mode: Literal["local"] = "local"


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(value))
    temporary.replace(path)


def _parse_time(value: object) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise SourceRoutingSessionError("Missing timestamp")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SourceRoutingSessionError(f"Invalid timestamp: {value!r}") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceRoutingSessionError(f"Cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise SourceRoutingSessionError(f"Expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SourceRoutingSessionError(f"Cannot read JSONL: {path}") from exc
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SourceRoutingSessionError(f"Malformed JSONL line {number}: {path}") from exc
        if not isinstance(value, dict):
            raise SourceRoutingSessionError(f"Non-object JSONL line {number}: {path}")
        rows.append(value)
    return rows


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceRoutingSessionError(f"Cannot read evidence list: {path}") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise SourceRoutingSessionError(f"Expected evidence-item list: {path}")
    return [dict(item) for item in value]


def _validate_selection(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> datetime:
    if len(rows) != TARGET_ROWS:
        raise SourceRoutingSessionError(f"Expected {TARGET_ROWS} selected rows; found {len(rows)}")
    if manifest.get("purpose") != EXPERIMENT_ID:
        raise SourceRoutingSessionError("Selection experiment identity changed")
    if manifest.get("protocol_commit") != PROTOCOL_COMMIT:
        raise SourceRoutingSessionError("Selection protocol identity changed")
    if manifest.get("preselection_model_manifest_sha256") != MODEL_MANIFEST_SHA256:
        raise SourceRoutingSessionError("Preselection model-manifest identity changed")
    if manifest.get("selected_rows") != TARGET_ROWS:
        raise SourceRoutingSessionError("Selection row count changed")
    for field in (
        "evidence_accessed",
        "model_forecast_run",
        "outcomes_accessed",
        "reserved_holdout_accessed",
    ):
        if manifest.get(field) is not False:
            raise SourceRoutingSessionError(f"Selection reports forbidden state: {field}")

    market_ids = [str(row.get("market_id") or "") for row in rows]
    event_ids = [str(row.get("event_id") or "") for row in rows]
    if any(not value for value in market_ids) or len(set(market_ids)) != TARGET_ROWS:
        raise SourceRoutingSessionError("Selected market IDs are not 12 unique values")
    if any(not value for value in event_ids) or len(set(event_ids)) != TARGET_ROWS:
        raise SourceRoutingSessionError("Selected event IDs are not 12 unique values")
    for row in rows:
        for field in ("question_text", "yes_token_id", "scheduled_end_at"):
            if not row.get(field):
                raise SourceRoutingSessionError(f"Selected row lacks {field}")
    return _parse_time(manifest.get("snapshot_reference_at"))


def _row_failure(row: dict[str, Any], *, status: str, detail: str) -> dict[str, object]:
    return {
        "market_id": str(row.get("market_id") or ""),
        "event_id": str(row.get("event_id") or ""),
        "question_id": f"polymarket-market:{row.get('market_id')}",
        "status": status,
        "detail": detail[:1000],
        "forecast_ready": False,
    }


def _packet(
    *,
    question_id: str,
    status: str,
    raw_items: list[dict[str, Any]],
    capture_completed_at: str,
    market_price_timestamp: str,
    condition: str,
) -> EvidencePacket:
    items = [
        EvidenceItem.from_dict(
            {
                "source_id": value.get("source_id"),
                "source_type": value.get("source_type"),
                "uri_or_reference": value.get("uri_or_reference"),
                "title": value.get("title"),
                "available_at": value.get("available_at"),
                "retrieved_at": capture_completed_at,
                "text": value.get("text"),
            }
        )
        for value in raw_items
    ]
    availability = EvidenceAvailability.from_dict(
        {
            "status": status,
            "detail": (
                f"Prospective v0.3 {condition} capture completed with retained evidence."
                if status == "verified_complete"
                else f"Prospective v0.3 {condition} capture completed with no retained evidence."
            ),
        },
        item_count=len(items),
    )
    return EvidencePacket.create(
        question_id=question_id,
        forecasted_at=market_price_timestamp,
        research_cutoff_at=market_price_timestamp,
        evidence_items=items,
        availability=availability,
    )


def _resolution_sources(row: dict[str, Any]) -> list[object]:
    value = row.get("resolution_sources")
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def run_acquisition(
    *,
    selected_candidates_path: Path,
    selection_manifest_path: Path,
    output_directory: Path,
    code_commit: str,
    rss_client: live_rss.GoogleNewsRssClient,
    source_client: routing.ResolutionSourceClient,
    market_client: v01.ClobClient,
    now: Any = None,
) -> dict[str, object]:
    """Freeze both evidence conditions before the market comparator for all rows."""
    if output_directory.exists():
        raise SourceRoutingSessionError("Refusing to replace existing v0.3 acquisition output")

    rows = _load_jsonl(selected_candidates_path)
    selection_manifest = _load_json(selection_manifest_path)
    selection_at = _validate_selection(rows, selection_manifest)
    clock = now or (lambda: datetime.now(UTC))

    output_directory.mkdir(parents=True)
    evidence_root = output_directory / "evidence"
    row_root = output_directory / "rows"
    records: list[dict[str, object]] = []

    for row in rows:
        market_id = str(row["market_id"])
        event_id = str(row["event_id"])
        question_id = f"polymarket-market:{market_id}"
        row_directory = row_root / v01._safe_market_id(market_id)
        row_directory.mkdir(parents=True)

        acquisition_clock = clock()
        if acquisition_clock.tzinfo is None:
            acquisition_clock = acquisition_clock.replace(tzinfo=UTC)
        selection_age = (acquisition_clock.astimezone(UTC) - selection_at).total_seconds()
        if selection_age < 0 or selection_age > SELECTION_TO_ACQUISITION_SECONDS:
            record = _row_failure(
                row,
                status="selection_window_failure",
                detail="Evidence capture did not begin inside the frozen 120-minute window.",
            )
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        capture = routing.capture_paired_evidence(
            question_id=question_id,
            question_text=str(row["question_text"]),
            resolution_sources=_resolution_sources(row),
            output_directory=evidence_root,
            rss_client=rss_client,
            source_client=source_client,
        )
        if capture.get("status") == "retrieval_failure":
            record = _row_failure(
                row,
                status="retrieval_failure",
                detail=str(capture.get("error") or "paired evidence capture failed"),
            )
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        try:
            bid_response = market_client.clob_price(str(row["yes_token_id"]), "BUY")
            ask_response = market_client.clob_price(str(row["yes_token_id"]), "SELL")
            midpoint_response = market_client.clob_midpoint(str(row["yes_token_id"]))
        except custody.ProspectiveCustodyError as exc:
            record = _row_failure(row, status="clob_transport_failure", detail=str(exc))
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        raw_clob = row_directory / "raw-clob"
        clob_receipts = {
            "bid": custody._freeze_response(raw_clob / "bid.json", bid_response),
            "ask": custody._freeze_response(raw_clob / "ask.json", ask_response),
            "midpoint": custody._freeze_response(raw_clob / "midpoint.json", midpoint_response),
        }
        try:
            bid, ask, midpoint, spread = v01._validate_clob(
                bid_response, ask_response, midpoint_response
            )
            bound_capture = live_rss.bind_market_snapshot(
                dict(capture), market_price_timestamp=midpoint_response.acquired_at
            )
        except (v01.SessionError, live_rss.LiveCaptureError) as exc:
            record = _row_failure(row, status="market_binding_failure", detail=str(exc))
            record["clob_receipts"] = clob_receipts
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        evidence_directory = evidence_root / routing._safe_name(question_id)
        condition_a_items = _load_json_list(evidence_directory / "condition-a-evidence.json")
        condition_b_items = _load_json_list(evidence_directory / "condition-b-evidence.json")
        condition_a_status = str(capture.get("condition_a_status") or "")
        condition_b_status = str(capture.get("condition_b_status") or "")
        if condition_a_status not in {"verified_complete", "verified_empty"}:
            raise SourceRoutingSessionError("Condition A has nonterminal availability")
        if condition_b_status not in {"verified_complete", "verified_empty"}:
            raise SourceRoutingSessionError("Condition B has nonterminal availability")

        completed_at = str(capture.get("capture_completed_at") or "")
        packet_a = _packet(
            question_id=question_id,
            status=condition_a_status,
            raw_items=condition_a_items,
            capture_completed_at=completed_at,
            market_price_timestamp=midpoint_response.acquired_at,
            condition="Condition A",
        )
        packet_b = _packet(
            question_id=question_id,
            status=condition_b_status,
            raw_items=condition_b_items,
            capture_completed_at=completed_at,
            market_price_timestamp=midpoint_response.acquired_at,
            condition="Condition B",
        )
        bound_row = {
            **row,
            "within_event_rank": 1,
            "market_probability": midpoint,
            "best_bid": bid,
            "best_ask": ask,
            "spread": spread,
            "market_price_timestamp": midpoint_response.acquired_at,
            "source_cutoff_at": midpoint_response.acquired_at,
        }

        _atomic_json(row_directory / "bound-row.json", bound_row)
        _atomic_json(row_directory / "condition-a-packet.json", packet_a.to_dict())
        _atomic_json(row_directory / "condition-b-packet.json", packet_b.to_dict())
        _atomic_json(row_directory / "bound-capture-manifest.json", bound_capture)

        record = {
            "market_id": market_id,
            "event_id": event_id,
            "question_id": question_id,
            "status": "forecast_ready",
            "forecast_ready": True,
            "market_price_timestamp": midpoint_response.acquired_at,
            "market_probability": midpoint,
            "condition_a_status": condition_a_status,
            "condition_b_status": condition_b_status,
            "condition_a_packet_hash": packet_a.packet_hash,
            "condition_b_packet_hash": packet_b.packet_hash,
            "condition_a_evidence_items": len(condition_a_items),
            "condition_b_evidence_items": len(condition_b_items),
            "condition_evidence_identical": condition_a_items == condition_b_items,
            "direct_source_attempts": int(capture.get("direct_source_attempts") or 0),
            "direct_source_successes": int(capture.get("direct_source_successes") or 0),
            "clob_receipts": clob_receipts,
        }
        _atomic_json(row_directory / "acquisition-record.json", record)
        records.append(record)

    counts = Counter(str(record["status"]) for record in records)
    ready = sum(1 for record in records if record.get("forecast_ready") is True)
    summary: dict[str, object] = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "protocol_commit": PROTOCOL_COMMIT,
        "code_commit": code_commit,
        "selection_manifest_sha256": _sha256(selection_manifest_path.read_bytes()),
        "selected_candidates_sha256": _sha256(selected_candidates_path.read_bytes()),
        "preselection_model_manifest_sha256": MODEL_MANIFEST_SHA256,
        "selected_rows": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "forecast_ready_rows": ready,
        "acquisition_success_floor": ACQUISITION_SUCCESS_FLOOR,
        "acquisition_operational_success": ready >= ACQUISITION_SUCCESS_FLOOR,
        "direct_source_attempts": sum(int(r.get("direct_source_attempts") or 0) for r in records),
        "direct_source_successes": sum(
            int(r.get("direct_source_successes") or 0) for r in records
        ),
        "identical_condition_rows": sum(
            bool(r.get("condition_evidence_identical")) for r in records
        ),
        "records": records,
        "model_forecast_run": False,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    _atomic_json(output_directory / "acquisition-summary.json", summary)
    return summary


def verify_model_set(*, base_url: str, output_directory: Path) -> dict[str, object]:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=30.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise SourceRoutingSessionError(f"Cannot verify local Ollama models: {exc}") from exc
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise SourceRoutingSessionError("Ollama tags response lacks model list")
    by_name = {
        str(item.get("name")): str(item.get("digest") or "")
        for item in models
        if isinstance(item, dict) and item.get("name")
    }
    verified: list[dict[str, str]] = []
    for tag, digest in FROZEN_MODELS:
        actual = by_name.get(tag, "")
        if actual.removeprefix("sha256:") != digest.removeprefix("sha256:"):
            raise SourceRoutingSessionError(
                f"Ollama model identity changed for {tag}: actual={actual!r}, expected={digest!r}"
            )
        verified.append({"tag": tag, "digest": digest})
    output_directory.mkdir(parents=True, exist_ok=True)
    raw = response.content
    (output_directory / "ollama-tags.json").write_bytes(raw)
    receipt = {
        "verified": True,
        "models": verified,
        "ollama_tags_sha256": _sha256(raw),
        "preselection_model_manifest_sha256": MODEL_MANIFEST_SHA256,
    }
    _atomic_json(output_directory / "model-verification.json", receipt)
    return receipt


def _load_pair(
    acquisition_directory: Path, market_id: str
) -> tuple[dict[str, Any], EvidencePacket, EvidencePacket]:
    row_directory = acquisition_directory / "rows" / v01._safe_market_id(market_id)
    row = _load_json(row_directory / "bound-row.json")
    packet_a = EvidencePacket.from_dict(_load_json(row_directory / "condition-a-packet.json"))
    packet_b = EvidencePacket.from_dict(_load_json(row_directory / "condition-b-packet.json"))
    return row, packet_a, packet_b


def run_forecasting(
    *,
    acquisition_directory: Path,
    output_directory: Path,
    code_commit: str,
    ollama_base_url: str = "http://127.0.0.1:11434",
) -> dict[str, object]:
    """Run every frozen model over both paired evidence conditions."""
    if output_directory.exists():
        raise SourceRoutingSessionError("Refusing to replace existing v0.3 forecast output")

    acquisition = _load_json(acquisition_directory / "acquisition-summary.json")
    if acquisition.get("experiment_id") != EXPERIMENT_ID:
        raise SourceRoutingSessionError("Acquisition experiment identity changed")
    if acquisition.get("protocol_commit") != PROTOCOL_COMMIT:
        raise SourceRoutingSessionError("Acquisition protocol identity changed")
    if acquisition.get("preselection_model_manifest_sha256") != MODEL_MANIFEST_SHA256:
        raise SourceRoutingSessionError("Acquisition model-manifest identity changed")
    if acquisition.get("outcomes_accessed") is not False:
        raise SourceRoutingSessionError("Acquisition reports outcome access")
    if acquisition.get("reserved_holdout_accessed") is not False:
        raise SourceRoutingSessionError("Acquisition reports holdout access")

    ready = int(acquisition.get("forecast_ready_rows") or 0)
    if ready < ACQUISITION_SUCCESS_FLOOR:
        raise SourceRoutingSessionError(
            f"Acquisition gate failed: {ready}/{TARGET_ROWS} forecast-ready rows"
        )

    output_directory.mkdir(parents=True)
    model_verification = verify_model_set(
        base_url=ollama_base_url,
        output_directory=output_directory / "model-verification",
    )

    acquisition_records = acquisition.get("records")
    if not isinstance(acquisition_records, list):
        raise SourceRoutingSessionError("Malformed acquisition record list")

    all_records: list[dict[str, object]] = []
    cell_summaries: dict[str, dict[str, object]] = {}

    for tag, digest in FROZEN_MODELS:
        metadata = _AdapterMetadata(immutable_version=digest)
        adapter = OllamaMarketResidualV2Adapter(
            model=tag,
            metadata=cast(Any, metadata),
            base_url=ollama_base_url,
            timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
        )
        per_condition_records: dict[str, list[dict[str, object]]] = {
            condition: [] for condition in CONDITIONS
        }
        try:
            for acquisition_record in acquisition_records:
                if not isinstance(acquisition_record, dict):
                    raise SourceRoutingSessionError("Malformed acquisition record")
                market_id = str(acquisition_record.get("market_id") or "")
                if acquisition_record.get("forecast_ready") is True:
                    row, packet_a, packet_b = _load_pair(acquisition_directory, market_id)
                    packets = {
                        "condition-a": packet_a,
                        "condition-b": packet_b,
                    }
                else:
                    row = {}
                    packets = {}

                for condition in CONDITIONS:
                    if acquisition_record.get("forecast_ready") is not True:
                        record: dict[str, object] = {
                            "model_tag": tag,
                            "model_digest": digest,
                            "condition": condition,
                            "market_id": market_id,
                            "event_id": str(acquisition_record.get("event_id") or ""),
                            "question_id": str(acquisition_record.get("question_id") or ""),
                            "status": "acquisition_failure_no_forecast",
                            "acquisition_status": str(acquisition_record.get("status") or ""),
                            "model_called": False,
                        }
                    else:
                        record = dict(
                            forecaster.forecast_row(
                                row,
                                packet=packets[condition],
                                adapter=adapter,
                            )
                        )
                        record["model_tag"] = tag
                        record["model_digest"] = digest
                        record["condition"] = condition

                    per_condition_records[condition].append(record)
                    all_records.append(record)
                    _atomic_json(
                        output_directory
                        / "forecasts"
                        / tag.replace(":", "_")
                        / condition
                        / f"{v01._safe_market_id(market_id)}.json",
                        record,
                    )
        finally:
            adapter.close()

        for condition in CONDITIONS:
            records = per_condition_records[condition]
            statuses = Counter(str(record.get("status") or "unknown") for record in records)
            actions = Counter(str(record.get("action") or "none") for record in records)
            strengths = Counter(
                str(record.get("evidence_strength") or "none") for record in records
            )
            terminal = sum(record.get("status") in TERMINAL_STATUSES for record in records)
            key = f"{tag}|{condition}"
            cell_summaries[key] = {
                "model_tag": tag,
                "model_digest": digest,
                "condition": condition,
                "terminal_forecast_rows": terminal,
                "status_counts": dict(sorted(statuses.items())),
                "action_counts": dict(sorted(actions.items())),
                "evidence_strength_counts": dict(sorted(strengths.items())),
                "operational_success": terminal == ready,
            }

    operational_success = all(
        bool(summary["operational_success"]) for summary in cell_summaries.values()
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "protocol_commit": PROTOCOL_COMMIT,
        "code_commit": code_commit,
        "acquisition_summary_sha256": _sha256(
            (acquisition_directory / "acquisition-summary.json").read_bytes()
        ),
        "model_manifest_sha256": MODEL_MANIFEST_SHA256,
        "model_verification": model_verification,
        "model_timeout_seconds": OLLAMA_TIMEOUT_SECONDS,
        "selected_rows": TARGET_ROWS,
        "forecast_ready_rows": ready,
        "conditions": list(CONDITIONS),
        "cells": cell_summaries,
        "records": all_records,
        "operational_success": operational_success,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    _atomic_json(output_directory / "forecast-summary.json", summary)
    if not operational_success:
        raise SourceRoutingSessionError("At least one frozen model-condition cell lacks terminal rows")
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("selected_candidates", type=Path)
    acquire.add_argument("selection_manifest", type=Path)
    acquire.add_argument("output_directory", type=Path)
    acquire.add_argument("--code-commit", required=True)
    forecast = subparsers.add_parser("forecast")
    forecast.add_argument("acquisition_directory", type=Path)
    forecast.add_argument("output_directory", type=Path)
    forecast.add_argument("--code-commit", required=True)
    forecast.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "acquire":
        with (
            live_rss.GoogleNewsRssClient() as rss_client,
            routing.ResolutionSourceClient() as source_client,
            custody.ProspectivePolymarketClient() as market_client,
        ):
            summary = run_acquisition(
                selected_candidates_path=args.selected_candidates,
                selection_manifest_path=args.selection_manifest,
                output_directory=args.output_directory,
                code_commit=args.code_commit,
                rss_client=rss_client,
                source_client=source_client,
                market_client=market_client,
            )
        safe = {
            "selected_rows": summary["selected_rows"],
            "forecast_ready_rows": summary["forecast_ready_rows"],
            "status_counts": summary["status_counts"],
            "acquisition_operational_success": summary["acquisition_operational_success"],
            "direct_source_attempts": summary["direct_source_attempts"],
            "direct_source_successes": summary["direct_source_successes"],
            "identical_condition_rows": summary["identical_condition_rows"],
            "outcomes_accessed": summary["outcomes_accessed"],
            "reserved_holdout_accessed": summary["reserved_holdout_accessed"],
        }
        print(json.dumps(safe, indent=2, sort_keys=True))
        return

    summary = run_forecasting(
        acquisition_directory=args.acquisition_directory,
        output_directory=args.output_directory,
        code_commit=args.code_commit,
        ollama_base_url=args.ollama_base_url,
    )
    safe = {
        "forecast_ready_rows": summary["forecast_ready_rows"],
        "cells": summary["cells"],
        "operational_success": summary["operational_success"],
        "outcomes_accessed": summary["outcomes_accessed"],
        "reserved_holdout_accessed": summary["reserved_holdout_accessed"],
    }
    print(json.dumps(safe, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
