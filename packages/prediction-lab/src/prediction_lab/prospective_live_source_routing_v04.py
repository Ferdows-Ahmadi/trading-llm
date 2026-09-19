"""Deterministic prevalidated selector for prospective live source routing v0.4."""

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

PROTOCOL_COMMIT = "24cb23281b0331ba5cbd3159cfc378733350248c"
MODEL_MANIFEST_SHA256 = "3cac3f0949f844e39fb052d104d2a284f4eeef2ba3c1674263c2ba99c4bfa514"
SELECTION_SEED = "prospective-live-source-routing-v0.4-selection-seed-2026-09-19"
PURPOSE = "prospective-live-source-routing-v0.4"
MIN_HORIZON = pd.Timedelta("7D")
MAX_HORIZON = pd.Timedelta("30D")
TARGET_COHORT = 12
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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _within_event_rank(item: dict[str, Any]) -> str:
    return base._rank(SELECTION_SEED, item["event_id"], item["market_id"])


def _global_rank(item: dict[str, Any]) -> str:
    return base._rank(SELECTION_SEED, "source-routing", item["event_id"], item["market_id"])


def _load_model_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise base.ProspectiveCustodyError(f"Cannot read frozen model manifest: {path}") from exc
    actual = _sha256(raw)
    if actual != MODEL_MANIFEST_SHA256:
        raise base.ProspectiveCustodyError(
            f"Frozen model manifest hash changed: {actual} != {MODEL_MANIFEST_SHA256}"
        )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise base.ProspectiveCustodyError("Frozen model manifest is malformed JSON") from exc
    if not isinstance(value, dict):
        raise base.ProspectiveCustodyError("Frozen model manifest must be a JSON object")
    if value.get("experiment_id") != PURPOSE:
        raise base.ProspectiveCustodyError("Frozen model manifest experiment identity changed")
    if value.get("stage") != "preselection-model-freeze":
        raise base.ProspectiveCustodyError("Frozen model manifest stage changed")
    for field in (
        "market_selection_run",
        "evidence_accessed",
        "model_forecast_run",
        "outcomes_accessed",
        "reserved_holdout_accessed",
    ):
        if value.get(field) is not False:
            raise base.ProspectiveCustodyError(
                f"Frozen model manifest reports forbidden preselection state: {field}"
            )
    models = value.get("models")
    expected = [{"tag": tag, "digest": digest} for tag, digest in FROZEN_MODELS]
    if models != expected:
        raise base.ProspectiveCustodyError("Frozen model identities changed")
    return value


def select_structural_candidates(eligible: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in eligible:
        groups.setdefault(str(item["event_id"]), []).append(item)

    representatives: list[dict[str, Any]] = []
    for event_id in sorted(groups):
        representative = min(groups[event_id], key=_within_event_rank)
        chosen = dict(representative)
        chosen["event_candidate_rank"] = _within_event_rank(representative)
        chosen["experiment_rank"] = _global_rank(representative)
        representatives.append(chosen)

    return sorted(representatives, key=lambda item: str(item["experiment_rank"]))[:TARGET_COHORT]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    payload = b"".join(base._canonical_bytes(row) + b"\n" for row in rows)
    path.write_bytes(payload)
    return _sha256(payload)


def collect_candidates(
    client: ProspectivePolymarketKeysetClient,
    *,
    model_manifest_path: Path,
    output_directory: Path,
    code_commit: str,
    snapshot_reference_at: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Run the first authorized v0.4 live step after validating the preselection freeze."""
    if output_directory.exists():
        raise base.ProspectiveCustodyError("Refusing to replace existing v0.4 selection")

    model_manifest = _load_model_manifest(model_manifest_path)

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
        base._iso_z(reference) + "\n", encoding="utf-8"
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
            entry["experiment_rank"] = _global_rank(normalized)
        ledger.append(entry)

    selected = select_structural_candidates(eligible)
    if len(selected) != TARGET_COHORT:
        raise base.ProspectiveCustodyError(
            f"Need {TARGET_COHORT} distinct eligible events; found {len(selected)}"
        )

    selected_ids = {str(item["market_id"]) for item in selected}
    for entry in ledger:
        if str(entry.get("market_id")) in selected_ids:
            entry["selected"] = True

    selected_rows = [
        {
            **base._contract_object(item),
            "category": item["category"],
            "volume_num": item["volume_num"],
            "liquidity_num": item["liquidity_num"],
            "selection_snapshot_at": base._iso_z(reference),
            "event_candidate_rank": item["event_candidate_rank"],
            "experiment_rank": item["experiment_rank"],
        }
        for item in selected
    ]

    universe_payload = b"".join(base._canonical_bytes(market) + b"\n" for market in universe)
    (output_directory / "universe-markets.jsonl").write_bytes(universe_payload)
    universe_sha256 = _sha256(universe_payload)
    ledger_sha256 = _write_jsonl(output_directory / "selection-ledger.jsonl", ledger)
    selected_sha256 = _write_jsonl(
        output_directory / "selected-candidates.jsonl", selected_rows
    )

    manifest: dict[str, object] = {
        "schema_version": 1,
        "purpose": PURPOSE,
        "protocol_commit": PROTOCOL_COMMIT,
        "code_commit": code_commit,
        "selection_seed": SELECTION_SEED,
        "preselection_model_manifest_sha256": MODEL_MANIFEST_SHA256,
        "preselection_model_frozen_at": model_manifest.get("frozen_at"),
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
        "evidence_accessed": False,
        "model_forecast_run": False,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
        "gamma_page_receipts": page_receipts,
    }
    (output_directory / "selection-manifest.json").write_bytes(
        base._canonical_bytes(manifest) + b"\n"
    )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    with ProspectivePolymarketKeysetClient() as client:
        manifest = collect_candidates(
            client,
            model_manifest_path=args.model_manifest,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
        )
    safe = {
        key: manifest[key]
        for key in (
            "purpose",
            "preselection_model_manifest_sha256",
            "snapshot_reference_at",
            "target_cohort",
            "universe_rows",
            "structurally_eligible_rows",
            "eligible_event_groups",
            "selected_rows",
            "selected_event_groups",
            "selected_candidates_sha256",
            "evidence_accessed",
            "model_forecast_run",
            "outcomes_accessed",
            "reserved_holdout_accessed",
        )
    }
    print(json.dumps(safe, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
