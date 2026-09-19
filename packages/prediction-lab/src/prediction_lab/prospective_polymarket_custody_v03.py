"""Preregistered clustered prospective development custody v0.3."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab import prospective_polymarket_custody_v02 as v02
from prediction_lab.prospective_polymarket_custody_keyset import (
    ProspectivePolymarketKeysetClient,
)

PROTOCOL_COMMIT = "a4de3487a3c931b9e04578b7a501aabb6050e0cc"
SELECTION_SEED = "prospective-development-custody-v0.3-selection-seed-2026-09-13"
PURPOSE = "prospective-development-custody-v0.3"
MIN_HORIZON = pd.Timedelta("7D")
MAX_HORIZON = pd.Timedelta("90D")
TARGET_COHORT = 80
MAX_PER_EVENT = 2
MARKET_FLOOR = 60
EVENT_CLUSTER_FLOOR = 40


def _candidate_rank(item: dict[str, Any]) -> str:
    return base._rank(SELECTION_SEED, item["event_id"], item["market_id"])


def _round_rank(item: dict[str, Any]) -> str:
    return base._rank(
        SELECTION_SEED,
        item["within_event_rank"],
        item["event_id"],
        item["market_id"],
    )


def _deterministic_event_candidates(
    eligible: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in eligible:
        groups.setdefault(str(item["event_id"]), []).append(item)

    candidates: list[dict[str, Any]] = []
    for event_id in sorted(groups):
        ranked = sorted(groups[event_id], key=_candidate_rank)
        for within_rank, item in enumerate(ranked[:MAX_PER_EVENT], start=1):
            item["within_event_rank"] = within_rank
            item["event_candidate_rank"] = _candidate_rank(item)
            candidates.append(item)
    return candidates, groups


def _select_clustered_cohort(
    clob_valid: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    for within_rank in range(1, MAX_PER_EVENT + 1):
        round_rows = [
            item
            for item in clob_valid
            if int(item["within_event_rank"]) == within_rank
        ]
        ordered.extend(sorted(round_rows, key=_round_rank))
    return ordered[:TARGET_COHORT]


def collect_prospective_custody_v03(
    client: ProspectivePolymarketKeysetClient,
    *,
    output_directory: Path,
    code_commit: str,
    snapshot_reference_at: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Run frozen v0.3 clustered custody without model inference."""
    if output_directory.exists():
        raise base.ProspectiveCustodyError("Refusing to replace existing custody output")
    output_directory.mkdir(parents=True)
    raw_gamma = output_directory / "raw" / "gamma"
    raw_clob = output_directory / "raw" / "clob"

    reference = (
        base._utc(snapshot_reference_at, field="snapshot_reference_at")
        if snapshot_reference_at is not None
        else pd.Timestamp.now(tz="UTC")
    )
    (output_directory / "snapshot-reference.txt").write_text(
        base._iso_z(reference) + "\n",
        encoding="utf-8",
    )
    earliest_end = reference + MIN_HORIZON
    latest_end = reference + MAX_HORIZON

    universe, page_receipts = v02._collect_keyset_universe(
        client,
        raw_gamma=raw_gamma,
        earliest_end=earliest_end,
        latest_end=latest_end,
    )

    ledger: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    seen_market_ids: set[str] = set()
    for index, market in enumerate(universe):
        market_id = base._text(market.get("id"))
        if market_id and market_id in seen_market_ids:
            raise base.ProspectiveCustodyError(
                f"Duplicate market ID in universe: {market_id}"
            )
        if market_id:
            seen_market_ids.add(market_id)

        normalized, reasons = base.structural_check(
            market,
            earliest_end=earliest_end,
            latest_end=latest_end,
        )
        entry: dict[str, Any] = {
            "universe_index": index,
            "market_id": market_id or None,
            "structural_eligible": normalized is not None,
            "structural_reason_codes": reasons,
            "event_candidate": False,
            "within_event_rank": None,
            "clob_status": "not_attempted",
            "clob_reason_codes": [],
            "selected": False,
        }
        if normalized is not None:
            entry.update(
                {
                    "event_id": normalized["event_id"],
                    "event_candidate_rank": _candidate_rank(normalized),
                }
            )
            normalized["ledger_index"] = len(ledger)
            eligible.append(normalized)
        ledger.append(entry)

    candidates, groups = _deterministic_event_candidates(eligible)
    candidate_ids = {str(item["market_id"]) for item in candidates}
    for item in eligible:
        entry = ledger[int(item["ledger_index"])]
        if str(item["market_id"]) in candidate_ids:
            entry["event_candidate"] = True
            entry["within_event_rank"] = int(item["within_event_rank"])
            entry["selection_reason_code"] = "deterministic_event_candidate"
        else:
            entry["selection_reason_code"] = "outside_within_event_cap"

    clob_valid: list[dict[str, Any]] = []
    clob_receipts: list[dict[str, object]] = []
    for item in candidates:
        ledger_entry = ledger[int(item["ledger_index"])]
        market_id = str(item["market_id"])
        yes_token = str(item["yes_token_id"])
        safe = base._safe_market_name(market_id)
        try:
            bid_response = client.clob_price(yes_token, "BUY")
            ask_response = client.clob_price(yes_token, "SELL")
            midpoint_response = client.clob_midpoint(yes_token)
        except base.ProspectiveCustodyError as exc:
            ledger_entry["clob_status"] = "transport_failure"
            ledger_entry["clob_reason_codes"] = ["clob_transport_failure"]
            ledger_entry["clob_error"] = str(exc)[:240]
            continue

        response_group = (
            ("bid", bid_response),
            ("ask", ask_response),
            ("midpoint", midpoint_response),
        )
        frozen: dict[str, dict[str, object]] = {}
        for label, response in response_group:
            receipt = base._freeze_response(
                raw_clob / f"{safe}-{label}.json",
                response,
            )
            receipt.update({"market_id": market_id, "kind": label})
            clob_receipts.append(receipt)
            frozen[label] = receipt

        bid = base._extract_price(bid_response, "price")
        ask = base._extract_price(ask_response, "price")
        midpoint, midpoint_reasons = v02._midpoint_value(midpoint_response)
        reasons = list(midpoint_reasons)
        values = (bid, ask, midpoint)
        if not reasons and any(
            value is None or not 0.0 < value < 1.0 for value in values
        ):
            reasons.append("invalid_clob_price")

        spread: float | None = None
        if not reasons:
            assert bid is not None and ask is not None and midpoint is not None
            spread = ask - bid
            if not bid <= midpoint <= ask:
                reasons.append("midpoint_outside_bid_ask")
            if spread < 0:
                reasons.append("negative_spread")
            elif spread - base.MAX_SPREAD > base._SPREAD_EPSILON:
                reasons.append("spread_above_maximum")

        if reasons:
            ledger_entry["clob_status"] = "rejected"
            ledger_entry["clob_reason_codes"] = reasons
            continue

        assert bid is not None and ask is not None and midpoint is not None
        assert spread is not None
        ledger_entry["clob_status"] = "valid"
        valid_item = dict(item)
        valid_item.update(
            {
                "best_bid": bid,
                "best_ask": ask,
                "market_probability": midpoint,
                "spread": spread,
                "market_price_timestamp": midpoint_response.acquired_at,
                "clob_receipts": frozen,
                "cohort_rank": _round_rank(item),
            }
        )
        clob_valid.append(valid_item)

    selected = _select_clustered_cohort(clob_valid)
    selected_ids = {str(item["market_id"]) for item in selected}
    for entry in ledger:
        market_id = str(entry.get("market_id"))
        if market_id in selected_ids:
            entry["selected"] = True
            entry["selection_reason_code"] = "selected_by_frozen_clustered_rank"
        elif entry.get("event_candidate") and entry.get("clob_status") == "valid":
            entry["selection_reason_code"] = "outside_target_rank"

    selected_rows: list[dict[str, Any]] = []
    for item in selected:
        contract = base._contract_object(item)
        selected_rows.append(
            {
                **contract,
                "category": item["category"],
                "volume_num": item["volume_num"],
                "liquidity_num": item["liquidity_num"],
                "within_event_rank": item["within_event_rank"],
                "snapshot_reference_at": base._iso_z(reference),
                "source_cutoff_at": base._iso_z(reference),
                "market_price_timestamp": item["market_price_timestamp"],
                "market_probability": item["market_probability"],
                "best_bid": item["best_bid"],
                "best_ask": item["best_ask"],
                "spread": item["spread"],
                "cohort_rank": item["cohort_rank"],
                "contract_sha256": base._sha256(base._canonical_bytes(contract)),
            }
        )

    universe_payload = b"".join(
        base._canonical_bytes(market) + b"\n" for market in universe
    )
    (output_directory / "universe-markets.jsonl").write_bytes(universe_payload)

    ledger_payload = b"".join(
        base._canonical_bytes(row) + b"\n" for row in ledger
    )
    (output_directory / "selection-ledger.jsonl").write_bytes(ledger_payload)

    cohort_payload = b"".join(
        base._canonical_bytes(row) + b"\n" for row in selected_rows
    )
    (output_directory / "cohort.jsonl").write_bytes(cohort_payload)

    receipts = {
        "gamma_keyset_pages": page_receipts,
        "clob_responses": clob_receipts,
    }
    receipts_path = output_directory / "acquisition-receipts.json"
    receipts_path.write_bytes(base._canonical_bytes(receipts) + b"\n")

    reason_counts: Counter[str] = Counter()
    for entry in ledger:
        if entry.get("event_candidate"):
            reason_counts.update(entry.get("clob_reason_codes") or [])

    selected_event_counts = Counter(str(row["event_id"]) for row in selected_rows)
    selected_rank_counts = Counter(
        int(row["within_event_rank"]) for row in selected_rows
    )
    cluster_size_counts = Counter(selected_event_counts.values())
    selected_event_groups = len(selected_event_counts)
    development_authorized = (
        len(selected_rows) >= MARKET_FLOOR
        and selected_event_groups >= EVENT_CLUSTER_FLOOR
    )

    summary: dict[str, object] = {
        "schema_version": 3,
        "purpose": PURPOSE,
        "protocol_commit": PROTOCOL_COMMIT,
        "code_commit": code_commit,
        "selection_seed": SELECTION_SEED,
        "pagination_mode": "gamma-markets-keyset-after_cursor",
        "keyset_max_pages": v02.MAX_PAGES,
        "snapshot_reference_at": base._iso_z(reference),
        "scheduled_end_min": base._iso_z(earliest_end),
        "scheduled_end_max": base._iso_z(latest_end),
        "gamma_pages": len(page_receipts),
        "universe_rows": len(universe),
        "structurally_eligible_markets": len(eligible),
        "structurally_eligible_event_groups": len(groups),
        "event_candidates": len(candidates),
        "candidate_event_groups": len({str(item["event_id"]) for item in candidates}),
        "clob_valid_candidates": len(clob_valid),
        "clob_transport_failures": sum(
            entry["clob_status"] == "transport_failure" for entry in ledger
        ),
        "clob_rejection_reason_counts": dict(sorted(reason_counts.items())),
        "selected_rows": len(selected_rows),
        "selected_event_groups": selected_event_groups,
        "selected_within_event_rank_counts": {
            str(key): value for key, value in sorted(selected_rank_counts.items())
        },
        "selected_event_cluster_size_counts": {
            str(key): value for key, value in sorted(cluster_size_counts.items())
        },
        "target_cohort": TARGET_COHORT,
        "max_per_event": MAX_PER_EVENT,
        "market_floor": MARKET_FLOOR,
        "event_cluster_floor": EVENT_CLUSTER_FLOOR,
        "development_forecaster_authorized": development_authorized,
        "confirmatory_edge_claim_authorized": False,
        "minimum_volume": base.MIN_VOLUME,
        "minimum_liquidity": base.MIN_LIQUIDITY,
        "maximum_spread": base.MAX_SPREAD,
        "universe_sha256": base._sha256(universe_payload),
        "selection_ledger_sha256": base._sha256(ledger_payload),
        "cohort_sha256": base._sha256(cohort_payload),
        "acquisition_receipts_sha256": base._sha256(receipts_path.read_bytes()),
        "forecaster_run": False,
        "model_score_computed": False,
        "reserved_holdout_accessed": False,
    }
    (output_directory / "custody-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()

    with ProspectivePolymarketKeysetClient() as client:
        summary = collect_prospective_custody_v03(
            client,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
        )

    safe_keys = (
        "snapshot_reference_at",
        "gamma_pages",
        "universe_rows",
        "structurally_eligible_markets",
        "structurally_eligible_event_groups",
        "event_candidates",
        "candidate_event_groups",
        "clob_valid_candidates",
        "clob_transport_failures",
        "clob_rejection_reason_counts",
        "selected_rows",
        "selected_event_groups",
        "selected_within_event_rank_counts",
        "selected_event_cluster_size_counts",
        "development_forecaster_authorized",
        "confirmatory_edge_claim_authorized",
        "universe_sha256",
        "selection_ledger_sha256",
        "cohort_sha256",
    )
    print(json.dumps({key: summary[key] for key in safe_keys}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
