"""Two-phase local runner for prospective live multimodel v0.2."""

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
from prediction_lab import prospective_live_enriched_v02 as enriched
from prediction_lab import prospective_live_multimodel_v02 as selector
from prediction_lab import prospective_live_rss_v01 as live_rss
from prediction_lab import prospective_live_session_v01 as v01
from prediction_lab import prospective_polymarket_custody as custody
from prediction_lab.research_types import EvidencePacket
from prediction_lab.residual_v2 import OllamaMarketResidualV2Adapter

EXPERIMENT_ID = "prospective-live-multimodel-v0.2"
PROTOCOL_COMMIT = selector.PROTOCOL_COMMIT
TARGET_ROWS = 12
ACQUISITION_SUCCESS_FLOOR = 10
SELECTION_TO_ACQUISITION_SECONDS = 120 * 60
OLLAMA_TIMEOUT_SECONDS = 1200.0
MODEL_MANIFEST_SHA256 = "296c91cbd22cd3d81b978f0c0a7499af8a54e9ecd8d76d20b8e6f2571691d40a"
FROZEN_MODELS: tuple[tuple[str, str], ...] = (
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


class MultimodelSessionError(RuntimeError):
    """Raised when the v0.2 experiment contract cannot be satisfied."""


@dataclass(frozen=True)
class _AdapterMetadata:
    """Minimal prospective metadata required by the legacy residual adapter."""

    immutable_version: str
    execution_mode: Literal["local"] = "local"


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(value))
    temporary.replace(path)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_time(value: object) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise MultimodelSessionError("Missing timestamp")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MultimodelSessionError(f"Invalid timestamp: {value!r}") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MultimodelSessionError(f"Cannot read JSON: {path}") from exc
    if not isinstance(value, dict):
        raise MultimodelSessionError(f"Expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MultimodelSessionError(f"Cannot read JSONL: {path}") from exc
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MultimodelSessionError(f"Malformed JSONL line {number}: {path}") from exc
        if not isinstance(value, dict):
            raise MultimodelSessionError(f"Non-object JSONL line {number}: {path}")
        rows.append(value)
    return rows


def _validate_selection(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> datetime:
    if len(rows) != TARGET_ROWS:
        raise MultimodelSessionError(f"Expected {TARGET_ROWS} selected rows; found {len(rows)}")
    if manifest.get("purpose") != EXPERIMENT_ID:
        raise MultimodelSessionError("Selection experiment identity changed")
    if manifest.get("protocol_commit") != PROTOCOL_COMMIT:
        raise MultimodelSessionError("Selection protocol identity changed")
    if manifest.get("selected_rows") != TARGET_ROWS:
        raise MultimodelSessionError("Selection row count changed")
    if manifest.get("evidence_accessed") is not False:
        raise MultimodelSessionError("Selection reports evidence access")
    if manifest.get("outcomes_accessed") is not False:
        raise MultimodelSessionError("Selection reports outcome access")
    if manifest.get("reserved_holdout_accessed") is not False:
        raise MultimodelSessionError("Selection reports holdout access")
    market_ids = [str(row.get("market_id") or "") for row in rows]
    event_ids = [str(row.get("event_id") or "") for row in rows]
    if any(not value for value in market_ids) or len(set(market_ids)) != TARGET_ROWS:
        raise MultimodelSessionError("Selected market IDs are not 12 unique non-empty values")
    if any(not value for value in event_ids) or len(set(event_ids)) != TARGET_ROWS:
        raise MultimodelSessionError("Selected event IDs are not 12 unique non-empty values")
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


def run_acquisition(
    *,
    selected_candidates_path: Path,
    selection_manifest_path: Path,
    output_directory: Path,
    code_commit: str,
    rss_client: live_rss.GoogleNewsRssClient,
    article_client: enriched.ArticleEnricher,
    market_client: v01.ClobClient,
    now: Any = None,
) -> dict[str, object]:
    if output_directory.exists():
        raise MultimodelSessionError("Refusing to replace existing v0.2 acquisition output")
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

        capture = enriched.capture_question(
            question_id=question_id,
            question_text=str(row["question_text"]),
            output_directory=evidence_root,
            rss_client=rss_client,
            article_client=article_client,
        )
        if capture.get("status") == "retrieval_failure":
            record = _row_failure(
                row,
                status="retrieval_failure",
                detail=str(capture.get("error") or "live evidence retrieval failed"),
            )
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        try:
            bid_response = market_client.clob_price(str(row["yes_token_id"]), "BUY")
            ask_response = market_client.clob_price(str(row["yes_token_id"]), "SELL")
            midpoint_response = market_client.clob_midpoint(str(row["yes_token_id"]))
        except custody.ProspectiveCustodyError as exc:
            record = _row_failure(
                row,
                status="clob_transport_failure",
                detail=str(exc),
            )
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
            record = _row_failure(
                row,
                status="market_binding_failure",
                detail=str(exc),
            )
            record["clob_receipts"] = clob_receipts
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        evidence_directory = evidence_root / hashlib.sha256(question_id.encode("utf-8")).hexdigest()
        raw_items_value = json.loads(
            (evidence_directory / "evidence.json").read_text(encoding="utf-8")
        )
        if not isinstance(raw_items_value, list) or not all(
            isinstance(value, dict) for value in raw_items_value
        ):
            raise MultimodelSessionError("Frozen enriched evidence payload is malformed")
        raw_items = [dict(value) for value in raw_items_value]
        packet = v01._evidence_packet(
            question_id=question_id,
            capture_manifest=bound_capture,
            raw_items=raw_items,
            market_price_timestamp=midpoint_response.acquired_at,
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
        _atomic_json(row_directory / "evidence-packet.json", packet.to_dict())
        _atomic_json(row_directory / "bound-capture-manifest.json", bound_capture)

        record = {
            "market_id": market_id,
            "event_id": event_id,
            "question_id": question_id,
            "status": "forecast_ready",
            "forecast_ready": True,
            "market_price_timestamp": midpoint_response.acquired_at,
            "market_probability": midpoint,
            "evidence_status": bound_capture["status"],
            "evidence_packet_hash": packet.packet_hash,
            "enrichment_attempts": capture.get("enrichment_attempts", 0),
            "enrichment_successes": capture.get("enrichment_successes", 0),
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
        "selected_rows": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "forecast_ready_rows": ready,
        "acquisition_success_floor": ACQUISITION_SUCCESS_FLOOR,
        "acquisition_operational_success": ready >= ACQUISITION_SUCCESS_FLOOR,
        "enrichment_attempts": sum(int(r.get("enrichment_attempts") or 0) for r in records),
        "enrichment_successes": sum(int(r.get("enrichment_successes") or 0) for r in records),
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
        raise MultimodelSessionError(f"Cannot verify local Ollama models: {exc}") from exc
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise MultimodelSessionError("Ollama tags response lacks model list")
    by_name = {
        str(item.get("name")): str(item.get("digest") or "")
        for item in models
        if isinstance(item, dict) and item.get("name")
    }
    verified: list[dict[str, str]] = []
    for tag, digest in FROZEN_MODELS:
        actual = by_name.get(tag, "")
        if actual.removeprefix("sha256:") != digest.removeprefix("sha256:"):
            raise MultimodelSessionError(
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


def _load_packet_and_row(
    acquisition_directory: Path, market_id: str
) -> tuple[dict[str, Any], EvidencePacket]:
    row_directory = acquisition_directory / "rows" / v01._safe_market_id(market_id)
    row = _load_json(row_directory / "bound-row.json")
    packet = EvidencePacket.from_dict(_load_json(row_directory / "evidence-packet.json"))
    return row, packet


def run_forecasting(
    *,
    acquisition_directory: Path,
    output_directory: Path,
    code_commit: str,
    ollama_base_url: str = "http://127.0.0.1:11434",
) -> dict[str, object]:
    if output_directory.exists():
        raise MultimodelSessionError("Refusing to replace existing v0.2 forecast output")
    acquisition = _load_json(acquisition_directory / "acquisition-summary.json")
    if acquisition.get("experiment_id") != EXPERIMENT_ID:
        raise MultimodelSessionError("Acquisition experiment identity changed")
    if acquisition.get("protocol_commit") != PROTOCOL_COMMIT:
        raise MultimodelSessionError("Acquisition protocol identity changed")
    if acquisition.get("outcomes_accessed") is not False:
        raise MultimodelSessionError("Acquisition reports outcome access")
    if acquisition.get("reserved_holdout_accessed") is not False:
        raise MultimodelSessionError("Acquisition reports holdout access")
    ready = int(acquisition.get("forecast_ready_rows") or 0)
    if ready < ACQUISITION_SUCCESS_FLOOR:
        raise MultimodelSessionError(
            f"Acquisition gate failed: {ready}/{TARGET_ROWS} forecast-ready rows"
        )

    output_directory.mkdir(parents=True)
    model_verification = verify_model_set(
        base_url=ollama_base_url,
        output_directory=output_directory / "model-verification",
    )

    acquisition_records = acquisition.get("records")
    if not isinstance(acquisition_records, list):
        raise MultimodelSessionError("Malformed acquisition record list")

    all_records: list[dict[str, object]] = []
    per_model: dict[str, dict[str, object]] = {}
    for tag, digest in FROZEN_MODELS:
        metadata = _AdapterMetadata(immutable_version=digest)
        adapter = OllamaMarketResidualV2Adapter(
            model=tag,
            metadata=cast(Any, metadata),
            base_url=ollama_base_url,
            timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
        )
        model_records: list[dict[str, object]] = []
        try:
            for acquisition_record in acquisition_records:
                if not isinstance(acquisition_record, dict):
                    raise MultimodelSessionError("Malformed acquisition record")
                market_id = str(acquisition_record.get("market_id") or "")
                if acquisition_record.get("forecast_ready") is not True:
                    record = {
                        "model_tag": tag,
                        "model_digest": digest,
                        "market_id": market_id,
                        "event_id": str(acquisition_record.get("event_id") or ""),
                        "question_id": str(acquisition_record.get("question_id") or ""),
                        "status": "acquisition_failure_no_forecast",
                        "acquisition_status": str(acquisition_record.get("status") or ""),
                        "model_called": False,
                    }
                else:
                    row, packet = _load_packet_and_row(acquisition_directory, market_id)
                    record = dict(forecaster.forecast_row(row, packet=packet, adapter=adapter))
                    record["model_tag"] = tag
                    record["model_digest"] = digest
                model_records.append(record)
                all_records.append(record)
                _atomic_json(
                    output_directory
                    / "forecasts"
                    / tag.replace(":", "_")
                    / f"{v01._safe_market_id(market_id)}.json",
                    record,
                )
        finally:
            adapter.close()

        terminal = sum(
            1
            for record in model_records
            if record.get("status")
            in {"model_evaluated", "model_failure_noop", "verified_empty_noop"}
        )
        statuses = Counter(str(record.get("status") or "unknown") for record in model_records)
        actions = Counter(str(record.get("action") or "none") for record in model_records)
        per_model[tag] = {
            "model_digest": digest,
            "terminal_forecast_rows": terminal,
            "status_counts": dict(sorted(statuses.items())),
            "action_counts": dict(sorted(actions.items())),
            "operational_success": terminal == ready,
        }

    operational_success = all(
        bool(summary["operational_success"]) for summary in per_model.values()
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
        "models": per_model,
        "records": all_records,
        "operational_success": operational_success,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    _atomic_json(output_directory / "forecast-summary.json", summary)
    if not operational_success:
        raise MultimodelSessionError("At least one frozen model lacks terminal records")
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
            enriched.ArticleEnricher() as article_client,
            custody.ProspectivePolymarketClient() as market_client,
        ):
            summary = run_acquisition(
                selected_candidates_path=args.selected_candidates,
                selection_manifest_path=args.selection_manifest,
                output_directory=args.output_directory,
                code_commit=args.code_commit,
                rss_client=rss_client,
                article_client=article_client,
                market_client=market_client,
            )
        safe = {
            "selected_rows": summary["selected_rows"],
            "forecast_ready_rows": summary["forecast_ready_rows"],
            "status_counts": summary["status_counts"],
            "acquisition_operational_success": summary["acquisition_operational_success"],
            "enrichment_attempts": summary["enrichment_attempts"],
            "enrichment_successes": summary["enrichment_successes"],
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
        "models": summary["models"],
        "operational_success": summary["operational_success"],
        "outcomes_accessed": summary["outcomes_accessed"],
        "reserved_holdout_accessed": summary["reserved_holdout_accessed"],
    }
    print(json.dumps(safe, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
