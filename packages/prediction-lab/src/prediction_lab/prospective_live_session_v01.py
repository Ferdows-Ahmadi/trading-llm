"""Two-phase local runner for prospective live-capture pilot v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from prediction_lab import prospective_forecast_v01 as forecaster
from prediction_lab import prospective_live_rss_v01 as live_rss
from prediction_lab import prospective_polymarket_custody as custody
from prediction_lab import prospective_polymarket_custody_v02 as custody_v02
from prediction_lab.research_types import EvidenceAvailability, EvidenceItem, EvidencePacket
from prediction_lab.residual_v2 import OllamaMarketResidualV2Adapter

EXPERIMENT_ID = "prospective-live-capture-pilot-v0.1"
PROTOCOL_COMMIT = "6bf0f71bb18641a5baf81764e41277bc00c3faa1"
OPERATIONAL_CLARIFICATION_COMMIT = "ab8bafa7bdd3ab9adea300278ac58f53f6d4ec4d"
TARGET_ROWS = 8
OPERATIONAL_SUCCESS_FLOOR = 7
SELECTION_TO_ACQUISITION_SECONDS = 120 * 60
OLLAMA_TIMEOUT_SECONDS = 1200.0
MODEL_TAG = forecaster.MODEL_TAG
MODEL_DIGEST = forecaster.MODEL_DIGEST


class SessionError(RuntimeError):
    """Raised when the live pilot session contract cannot be satisfied."""


class ClobClient(Protocol):
    def clob_price(self, token_id: str, side: str) -> custody.FrozenResponse: ...

    def clob_midpoint(self, token_id: str) -> custody.FrozenResponse: ...


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
        raise SessionError("Missing timestamp")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SessionError(f"Invalid timestamp: {value!r}") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_market_id(market_id: str) -> str:
    return custody._safe_market_name(market_id)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionError(f"Cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise SessionError(f"Expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SessionError(f"Cannot read JSONL: {path}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SessionError(f"Malformed JSONL line {line_number}: {path}") from exc
        if not isinstance(value, dict):
            raise SessionError(f"Non-object JSONL line {line_number}: {path}")
        rows.append(value)
    return rows


def _validate_selection(
    rows: list[dict[str, Any]],
    selection_manifest: Mapping[str, Any],
) -> datetime:
    if len(rows) != TARGET_ROWS:
        raise SessionError(f"Expected {TARGET_ROWS} selected rows; found {len(rows)}")
    if selection_manifest.get("purpose") != EXPERIMENT_ID:
        raise SessionError("Selection experiment identity changed")
    if selection_manifest.get("protocol_commit") != PROTOCOL_COMMIT:
        raise SessionError("Selection protocol identity changed")
    if selection_manifest.get("selected_rows") != TARGET_ROWS:
        raise SessionError("Selection manifest row count changed")
    if selection_manifest.get("evidence_accessed") is not False:
        raise SessionError("Selection reports evidence access")
    if selection_manifest.get("outcomes_accessed") is not False:
        raise SessionError("Selection reports outcome access")
    if selection_manifest.get("reserved_holdout_accessed") is not False:
        raise SessionError("Selection reports holdout access")

    market_ids = [str(row.get("market_id") or "") for row in rows]
    event_ids = [str(row.get("event_id") or "") for row in rows]
    if any(not value for value in market_ids) or len(set(market_ids)) != TARGET_ROWS:
        raise SessionError("Selected market IDs must be unique and non-empty")
    if any(not value for value in event_ids) or len(set(event_ids)) != TARGET_ROWS:
        raise SessionError("Pilot requires eight distinct parent events")
    for row in rows:
        for field in (
            "question_text",
            "description",
            "scheduled_end_at",
            "yes_token_id",
            "resolution_sources",
        ):
            if not row.get(field):
                raise SessionError(f"Selected row lacks {field}")
    return _parse_time(selection_manifest.get("snapshot_reference_at"))


def _validate_clob(
    bid_response: custody.FrozenResponse,
    ask_response: custody.FrozenResponse,
    midpoint_response: custody.FrozenResponse,
) -> tuple[float, float, float, float]:
    bid = custody._extract_price(bid_response, "price")
    ask = custody._extract_price(ask_response, "price")
    midpoint, midpoint_reasons = custody_v02._midpoint_value(midpoint_response)
    reasons = list(midpoint_reasons)
    values = (bid, ask, midpoint)
    if not reasons and any(value is None or not 0.0 < value < 1.0 for value in values):
        reasons.append("invalid_clob_price")
    if reasons:
        raise SessionError("Invalid CLOB snapshot: " + ",".join(reasons))
    assert bid is not None and ask is not None and midpoint is not None
    spread = ask - bid
    if not bid <= midpoint <= ask:
        raise SessionError("Invalid CLOB snapshot: midpoint_outside_bid_ask")
    if spread < 0:
        raise SessionError("Invalid CLOB snapshot: negative_spread")
    if spread - custody.MAX_SPREAD > custody._SPREAD_EPSILON:
        raise SessionError("Invalid CLOB snapshot: spread_above_maximum")
    return bid, ask, midpoint, spread


def _evidence_packet(
    *,
    question_id: str,
    capture_manifest: Mapping[str, Any],
    raw_items: list[dict[str, Any]],
    market_price_timestamp: str,
) -> EvidencePacket:
    status = str(capture_manifest.get("status") or "")
    completed_at = str(capture_manifest.get("capture_completed_at") or "")
    items: list[EvidenceItem] = []
    for value in raw_items:
        items.append(
            EvidenceItem.from_dict(
                {
                    "source_id": value.get("source_id"),
                    "source_type": value.get("source_type"),
                    "uri_or_reference": value.get("uri_or_reference"),
                    "title": value.get("title"),
                    "available_at": value.get("available_at"),
                    "retrieved_at": completed_at,
                    "text": value.get("text"),
                }
            )
        )
    availability = EvidenceAvailability.from_dict(
        {
            "status": status,
            "detail": (
                "Live Google News RSS capture completed with retained evidence."
                if status == "verified_complete"
                else "Live Google News RSS capture completed with no retained evidence."
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


def _row_failure(
    row: Mapping[str, Any],
    *,
    status: str,
    detail: str,
) -> dict[str, object]:
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
    market_client: ClobClient,
    now: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Freeze evidence and comparator snapshots for all selected rows before inference."""
    if output_directory.exists():
        raise SessionError("Refusing to replace existing acquisition output")
    rows = _load_jsonl(selected_candidates_path)
    selection_manifest = _load_json_object(selection_manifest_path)
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
        row_directory = row_root / _safe_market_id(market_id)
        row_directory.mkdir(parents=True)

        acquisition_clock = clock()
        if acquisition_clock.tzinfo is None:
            acquisition_clock = acquisition_clock.replace(tzinfo=UTC)
        acquisition_clock = acquisition_clock.astimezone(UTC)
        selection_age = (acquisition_clock - selection_at).total_seconds()
        if selection_age < 0 or selection_age > SELECTION_TO_ACQUISITION_SECONDS:
            record = _row_failure(
                row,
                status="selection_window_failure",
                detail=(
                    "Evidence capture did not begin inside the frozen 120-minute "
                    "selection-to-acquisition window."
                ),
            )
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        capture = live_rss.capture_question(
            question_id=question_id,
            question_text=str(row["question_text"]),
            output_directory=evidence_root,
            client=rss_client,
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
            "midpoint": custody._freeze_response(
                raw_clob / "midpoint.json",
                midpoint_response,
            ),
        }
        try:
            bid, ask, midpoint, spread = _validate_clob(
                bid_response,
                ask_response,
                midpoint_response,
            )
            bound_capture = live_rss.bind_market_snapshot(
                dict(capture),
                market_price_timestamp=midpoint_response.acquired_at,
            )
        except (SessionError, live_rss.LiveCaptureError) as exc:
            record = _row_failure(
                row,
                status="market_binding_failure",
                detail=str(exc),
            )
            record["clob_receipts"] = clob_receipts
            _atomic_json(row_directory / "acquisition-record.json", record)
            records.append(record)
            continue

        evidence_directory = evidence_root / hashlib.sha256(
            question_id.encode("utf-8")
        ).hexdigest()
        raw_items_value = json.loads(
            (evidence_directory / "evidence.json").read_text(encoding="utf-8")
        )
        if not isinstance(raw_items_value, list) or not all(
            isinstance(value, dict) for value in raw_items_value
        ):
            raise SessionError("Frozen RSS evidence payload is malformed")
        raw_items = [dict(value) for value in raw_items_value]
        packet = _evidence_packet(
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
            "detail": "Terminal live evidence and valid post-evidence CLOB snapshot frozen.",
            "forecast_ready": True,
            "market_price_timestamp": midpoint_response.acquired_at,
            "market_probability": midpoint,
            "evidence_status": bound_capture["status"],
            "evidence_packet_hash": packet.packet_hash,
            "clob_receipts": clob_receipts,
        }
        _atomic_json(row_directory / "acquisition-record.json", record)
        records.append(record)

    counts = Counter(str(record["status"]) for record in records)
    summary: dict[str, object] = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "protocol_commit": PROTOCOL_COMMIT,
        "operational_clarification_commit": OPERATIONAL_CLARIFICATION_COMMIT,
        "code_commit": code_commit,
        "selection_manifest_sha256": _sha256(selection_manifest_path.read_bytes()),
        "selected_candidates_sha256": _sha256(selected_candidates_path.read_bytes()),
        "selected_rows": len(rows),
        "status_counts": dict(sorted(counts.items())),
        "forecast_ready_rows": sum(
            1 for record in records if record.get("forecast_ready") is True
        ),
        "records": records,
        "model_forecast_run": False,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    _atomic_json(output_directory / "acquisition-summary.json", summary)
    return summary


def verify_ollama_model(
    *,
    base_url: str,
    output_directory: Path,
    client: httpx.Client | None = None,
) -> dict[str, object]:
    owns_client = client is None
    http = client or httpx.Client(timeout=30.0, follow_redirects=False)
    try:
        response = http.get(f"{base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        raw = response.content
        output_directory.mkdir(parents=True, exist_ok=True)
        (output_directory / "ollama-tags.json").write_bytes(raw)
        try:
            value = response.json()
        except json.JSONDecodeError as exc:
            raise SessionError("Ollama /api/tags returned malformed JSON") from exc
        models = value.get("models") if isinstance(value, dict) else None
        if not isinstance(models, list):
            raise SessionError("Ollama tag listing is missing models")
        match = next(
            (
                item
                for item in models
                if isinstance(item, dict) and item.get("name") == MODEL_TAG
            ),
            None,
        )
        if match is None:
            raise SessionError(f"Required Ollama model is missing: {MODEL_TAG}")
        actual = str(match.get("digest") or "")
        expected = MODEL_DIGEST.removeprefix("sha256:")
        if actual.removeprefix("sha256:") != expected:
            raise SessionError(
                f"Ollama model digest changed: actual={actual!r}, expected={expected!r}"
            )
        receipt = {
            "model_tag": MODEL_TAG,
            "model_digest": MODEL_DIGEST,
            "ollama_tags_sha256": _sha256(raw),
            "verified": True,
        }
        _atomic_json(output_directory / "model-verification.json", receipt)
        return receipt
    except httpx.HTTPError as exc:
        raise SessionError(f"Cannot verify local Ollama model: {exc}") from exc
    finally:
        if owns_client:
            http.close()


def run_forecasting(
    *,
    acquisition_directory: Path,
    output_directory: Path,
    code_commit: str,
    ollama_base_url: str = "http://127.0.0.1:11434",
) -> dict[str, object]:
    """Forecast only from already-frozen acquisition rows."""
    if output_directory.exists():
        raise SessionError("Refusing to replace existing forecast output")
    acquisition_summary = _load_json_object(
        acquisition_directory / "acquisition-summary.json"
    )
    if acquisition_summary.get("experiment_id") != EXPERIMENT_ID:
        raise SessionError("Acquisition experiment identity changed")
    if acquisition_summary.get("model_forecast_run") is not False:
        raise SessionError("Acquisition unexpectedly reports prior model execution")
    if acquisition_summary.get("outcomes_accessed") is not False:
        raise SessionError("Acquisition reports outcome access")
    if acquisition_summary.get("reserved_holdout_accessed") is not False:
        raise SessionError("Acquisition reports holdout access")

    output_directory.mkdir(parents=True)
    model_receipt = verify_ollama_model(
        base_url=ollama_base_url,
        output_directory=output_directory / "model",
    )

    metadata = forecaster._model_metadata()
    adapter = OllamaMarketResidualV2Adapter(
        model=MODEL_TAG,
        metadata=metadata,
        base_url=ollama_base_url,
        timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
    )
    records: list[dict[str, object]] = []
    try:
        for acquisition in acquisition_summary.get("records", []):
            if not isinstance(acquisition, dict):
                raise SessionError("Malformed acquisition record")
            market_id = str(acquisition.get("market_id") or "")
            if acquisition.get("forecast_ready") is not True:
                records.append(
                    {
                        "market_id": market_id,
                        "event_id": str(acquisition.get("event_id") or ""),
                        "question_id": str(acquisition.get("question_id") or ""),
                        "status": "acquisition_failure_no_forecast",
                        "acquisition_status": str(acquisition.get("status") or ""),
                        "model_called": False,
                    }
                )
                continue

            row_directory = acquisition_directory / "rows" / _safe_market_id(market_id)
            row = _load_json_object(row_directory / "bound-row.json")
            packet = EvidencePacket.from_dict(
                _load_json_object(row_directory / "evidence-packet.json")
            )
            forecast = forecaster.forecast_row(row, packet=packet, adapter=adapter)
            forecast_path = output_directory / "forecasts" / f"{_safe_market_id(market_id)}.json"
            _atomic_json(forecast_path, forecast)
            records.append(forecast)
    finally:
        adapter.close()

    terminal_forecasts = sum(
        1
        for record in records
        if record.get("status")
        in {"model_evaluated", "model_failure_noop", "verified_empty_noop"}
    )
    operational_success = terminal_forecasts >= OPERATIONAL_SUCCESS_FLOOR
    status_counts = Counter(str(record.get("status") or "unknown") for record in records)
    summary: dict[str, object] = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "protocol_commit": PROTOCOL_COMMIT,
        "operational_clarification_commit": OPERATIONAL_CLARIFICATION_COMMIT,
        "code_commit": code_commit,
        "acquisition_summary_sha256": _sha256(
            (acquisition_directory / "acquisition-summary.json").read_bytes()
        ),
        "model": model_receipt,
        "model_timeout_seconds": OLLAMA_TIMEOUT_SECONDS,
        "rows": len(records),
        "terminal_forecast_rows": terminal_forecasts,
        "operational_success_floor": OPERATIONAL_SUCCESS_FLOOR,
        "operational_success": operational_success,
        "status_counts": dict(sorted(status_counts.items())),
        "records": records,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    _atomic_json(output_directory / "forecast-summary.json", summary)
    if not operational_success:
        raise SessionError(
            f"Pilot failed operational gate: {terminal_forecasts}/{TARGET_ROWS} terminal forecasts"
        )
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
    forecast.add_argument(
        "--ollama-base-url",
        default="http://127.0.0.1:11434",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "acquire":
        with (
            live_rss.GoogleNewsRssClient() as rss_client,
            custody.ProspectivePolymarketClient() as market_client,
        ):
            summary = run_acquisition(
                selected_candidates_path=args.selected_candidates,
                selection_manifest_path=args.selection_manifest,
                output_directory=args.output_directory,
                code_commit=args.code_commit,
                rss_client=rss_client,
                market_client=market_client,
            )
        safe = {
            "selected_rows": summary["selected_rows"],
            "status_counts": summary["status_counts"],
            "forecast_ready_rows": summary["forecast_ready_rows"],
            "model_forecast_run": summary["model_forecast_run"],
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
        "rows": summary["rows"],
        "terminal_forecast_rows": summary["terminal_forecast_rows"],
        "operational_success": summary["operational_success"],
        "status_counts": summary["status_counts"],
        "outcomes_accessed": summary["outcomes_accessed"],
        "reserved_holdout_accessed": summary["reserved_holdout_accessed"],
    }
    print(json.dumps(safe, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
