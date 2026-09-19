"""Deterministic structural selector for prospective live-capture pilot v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab import prospective_polymarket_custody_v02 as v02
from prediction_lab.prospective_polymarket_custody_keyset import (
    ProspectivePolymarketKeysetClient,
)

PROTOCOL_COMMIT = "6bf0f71bb18641a5baf81764e41277bc00c3faa1"
SELECTION_SEED = "prospective-live-capture-pilot-v0.1-selection-seed-2026-09-15"
PURPOSE = "prospective-live-capture-pilot-v0.1"
MIN_HORIZON = pd.Timedelta("7D")
MAX_HORIZON = pd.Timedelta("30D")
TARGET_COHORT = 8


def _within_event_rank(item: dict[str, Any]) -> str:
    return base._rank(SELECTION_SEED, item["event_id"], item["market_id"])


def _global_rank(item: dict[str, Any]) -> str:
    return base._rank(SELECTION_SEED, "pilot", item["event_id"], item["market_id"])


def select_structural_candidates(
    eligible: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Choose one deterministic representative per event, then first eight globally."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in eligible:
        groups.setdefault(str(item["event_id"]), []).append(item)

    representatives: list[dict[str, Any]] = []
    for event_id in sorted(groups):
        representative = min(groups[event_id], key=_within_event_rank)
        chosen = dict(representative)
        chosen["event_candidate_rank"] = _within_event_rank(representative)
        chosen["pilot_rank"] = _global_rank(representative)
        representatives.append(chosen)

    return sorted(representatives, key=lambda item: str(item["pilot_rank"]))[:TARGET_COHORT]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    payload = b"".join(base._canonical_bytes(row) + b"\n" for row in rows)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def collect_pilot_candidates(
    client: ProspectivePolymarketKeysetClient,
    *,
    output_directory: Path,
    code_commit: str,
    snapshot_reference_at: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Freeze a fresh structural-only pilot selection before any evidence lookup."""
    if output_directory.exists():
        raise base.ProspectiveCustodyError("Refusing to replace existing pilot selection")
    output_directory.mkdir(parents=True)
    raw_gamma = output_directory / "raw" / "gamma"

    reference = (
        base._utc(snapshot_reference_at, field="snapshot_reference_at")
        if snapshot_reference_at is not None
        else pd.Timestamp.now(tz="UTC")
    )
    earliest_end = reference + MIN_HORIZON
    latest_end = reference + MAX_HORIZON

    (output_directory / "snapshot-reference.txt").write_text(
        base._iso_z(reference) + "\n",
        encoding="utf-8",
    )

    universe, page_receipts = v02._collect_keyset_universe(
        client,
        raw_gamma=raw_gamma,
        earliest_end=earliest_end,
        latest_end=latest_end,
    )

    eligible: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for index, market in enumerate(universe):
        normalized, reasons = base.structural_check(
            market,
            earliest_end=earliest_end,
            latest_end=latest_end,
        )
        entry: dict[str, Any] = {
            "universe_index": index,
            "market_id": base._text(market.get("id")) or None,
            "structural_eligible": normalized is not None,
            "structural_reason_codes": reasons,
            "selected": False,
        }
        if normalized is not None:
            eligible.append(normalized)
            entry["event_id"] = normalized["event_id"]
            entry["event_candidate_rank"] = _within_event_rank(normalized)
            entry["pilot_rank"] = _global_rank(normalized)
        ledger.append(entry)

    selected = select_structural_candidates(eligible)
    selected_ids = {str(item["market_id"]) for item in selected}
    for entry in ledger:
        if str(entry.get("market_id")) in selected_ids:
            entry["selected"] = True

    selected_rows: list[dict[str, Any]] = []
    for item in selected:
        selected_rows.append(
            {
                **base._contract_object(item),
                "category": item["category"],
                "volume_num": item["volume_num"],
                "liquidity_num": item["liquidity_num"],
                "selection_snapshot_at": base._iso_z(reference),
                "event_candidate_rank": item["event_candidate_rank"],
                "pilot_rank": item["pilot_rank"],
            }
        )

    universe_payload = b"".join(
        base._canonical_bytes(market) + b"\n" for market in universe
    )
    (output_directory / "universe-markets.jsonl").write_bytes(universe_payload)
    universe_sha256 = hashlib.sha256(universe_payload).hexdigest()
    ledger_sha256 = _write_jsonl(output_directory / "selection-ledger.jsonl", ledger)
    selected_sha256 = _write_jsonl(
        output_directory / "selected-candidates.jsonl",
        selected_rows,
    )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "purpose": PURPOSE,
        "protocol_commit": PROTOCOL_COMMIT,
        "code_commit": code_commit,
        "selection_seed": SELECTION_SEED,
        "snapshot_reference_at": base._iso_z(reference),
        "scheduled_end_min": base._iso_z(earliest_end),
        "scheduled_end_max": base._iso_z(latest_end),
        "target_cohort": TARGET_COHORT,
        "universe_rows": len(universe),
        "structurally_eligible_rows": len(eligible),
        "eligible_event_groups": len({str(item["event_id"]) for item in eligible}),
        "selected_rows": len(selected_rows),
        "selected_event_groups": len({str(item["event_id"]) for item in selected}),
        "universe_sha256": universe_sha256,
        "selection_ledger_sha256": ledger_sha256,
        "selected_candidates_sha256": selected_sha256,
        "gamma_page_receipts": page_receipts,
        "evidence_accessed": False,
        "model_forecast_run": False,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    (output_directory / "selection-manifest.json").write_bytes(
        base._canonical_bytes(manifest) + b"\n"
    )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    with ProspectivePolymarketKeysetClient() as client:
        manifest = collect_pilot_candidates(
            client,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
        )
    safe_summary = {
        key: manifest[key]
        for key in (
            "purpose",
            "snapshot_reference_at",
            "target_cohort",
            "universe_rows",
            "structurally_eligible_rows",
            "eligible_event_groups",
            "selected_rows",
            "selected_event_groups",
            "universe_sha256",
            "selection_ledger_sha256",
            "selected_candidates_sha256",
            "evidence_accessed",
            "model_forecast_run",
            "outcomes_accessed",
            "reserved_holdout_accessed",
        )
    }
    print(json.dumps(safe_summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
