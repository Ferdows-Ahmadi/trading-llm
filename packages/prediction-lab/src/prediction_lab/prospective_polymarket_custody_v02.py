"""Preregistered prospective Polymarket development custody v0.2."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab.prospective_polymarket_custody_keyset import (
    ProspectivePolymarketKeysetClient,
)

PROTOCOL_COMMIT = "12a39fcc156ace92356e3d6b05b7a444f6c23679"
SELECTION_SEED = "prospective-development-custody-v0.2-selection-seed-2026-09-13"
PURPOSE = "prospective-development-custody-v0.2"
MIN_HORIZON = pd.Timedelta("7D")
MAX_HORIZON = pd.Timedelta("90D")
PAGE_SIZE = 100
MAX_PAGES = 1000
TARGET_COHORT = 100
ADEQUACY_FLOOR = 60


def _decimal(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not number.is_finite():
        return None
    return number


def _midpoint_value(response: base.FrozenResponse) -> tuple[float | None, list[str]]:
    """Parse the frozen v0.2 midpoint aliases without discretionary fallback."""
    if not isinstance(response.payload, dict):
        return None, ["missing_midpoint_field"]

    has_mid = "mid" in response.payload
    has_mid_price = "mid_price" in response.payload
    if not has_mid and not has_mid_price:
        return None, ["missing_midpoint_field"]

    if has_mid and has_mid_price:
        mid = _decimal(response.payload.get("mid"))
        mid_price = _decimal(response.payload.get("mid_price"))
        if mid is None or mid_price is None:
            return None, ["invalid_clob_price"]
        if mid != mid_price:
            return None, ["conflicting_midpoint_aliases"]
        return float(mid), []

    key = "mid" if has_mid else "mid_price"
    value = _decimal(response.payload.get(key))
    if value is None:
        return None, ["invalid_clob_price"]
    return float(value), []


def _collect_keyset_universe(
    client: ProspectivePolymarketKeysetClient,
    *,
    raw_gamma: Path,
    earliest_end: pd.Timestamp,
    latest_end: pd.Timestamp,
) -> tuple[list[dict[str, Any]], list[dict[str, object]]]:
    universe: list[dict[str, Any]] = []
    receipts: list[dict[str, object]] = []
    seen_cursors: set[str] = set()
    seen_market_ids: set[str] = set()
    after_cursor: str | None = None

    for page_index in range(MAX_PAGES):
        params: dict[str, object] = {
            "closed": "false",
            "end_date_min": base._iso_z(earliest_end),
            "end_date_max": base._iso_z(latest_end),
            "order": "id",
            "ascending": "true",
            "limit": PAGE_SIZE,
        }
        if after_cursor is not None:
            params["after_cursor"] = after_cursor

        response = client.gamma_markets_keyset_page(params)
        if not isinstance(response.payload, dict):
            raise base.ProspectiveCustodyError(
                "Gamma /markets/keyset response must be an object"
            )
        markets = response.payload.get("markets")
        if not isinstance(markets, list):
            raise base.ProspectiveCustodyError(
                "Gamma /markets/keyset response has no markets array"
            )

        raw_next = response.payload.get("next_cursor")
        if raw_next is None or raw_next == "":
            next_cursor: str | None = None
        elif isinstance(raw_next, str):
            next_cursor = raw_next
        else:
            raise base.ProspectiveCustodyError(
                "Gamma /markets/keyset next_cursor must be a string"
            )

        receipt = base._freeze_response(
            raw_gamma / f"page-{page_index:03d}.json",
            response,
        )
        receipt.update(
            {
                "page_index": page_index,
                "row_count": len(markets),
                "after_cursor_present": after_cursor is not None,
                "next_cursor_present": next_cursor is not None,
            }
        )
        if next_cursor is not None:
            receipt["next_cursor_sha256"] = base._sha256(next_cursor.encode("utf-8"))
        receipts.append(receipt)

        for market in markets:
            if not isinstance(market, dict):
                continue
            market_id = base._text(market.get("id"))
            if market_id:
                if market_id in seen_market_ids:
                    raise base.ProspectiveCustodyError(
                        f"Duplicate market ID across keyset pages: {market_id}"
                    )
                seen_market_ids.add(market_id)
            universe.append(market)

        if next_cursor is None:
            return universe, receipts
        if next_cursor in seen_cursors:
            raise base.ProspectiveCustodyError("Gamma keyset cursor repeated")
        seen_cursors.add(next_cursor)
        after_cursor = next_cursor

    raise base.ProspectiveCustodyError(
        f"Gamma keyset pagination hit {MAX_PAGES}-page safety limit"
    )


def collect_prospective_custody_v02(
    client: ProspectivePolymarketKeysetClient,
    *,
    output_directory: Path,
    code_commit: str,
    snapshot_reference_at: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Run the frozen v0.2 custody acquisition without model inference."""
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

    universe, page_receipts = _collect_keyset_universe(
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
            "event_representative": False,
            "clob_status": "not_attempted",
            "clob_reason_codes": [],
            "selected": False,
        }
        if normalized is not None:
            entry.update(
                {
                    "event_id": normalized["event_id"],
                    "event_rank": base._rank(
                        SELECTION_SEED,
                        normalized["event_id"],
                        normalized["market_id"],
                    ),
                }
            )
            normalized["ledger_index"] = len(ledger)
            eligible.append(normalized)
        ledger.append(entry)

    groups: dict[str, list[dict[str, Any]]] = {}
    for item in eligible:
        groups.setdefault(str(item["event_id"]), []).append(item)

    representatives: list[dict[str, Any]] = []
    for event_id in sorted(groups):
        representative = min(
            groups[event_id],
            key=lambda item: base._rank(
                SELECTION_SEED,
                item["event_id"],
                item["market_id"],
            ),
        )
        representatives.append(representative)
        ledger[int(representative["ledger_index"])]["event_representative"] = True
        for item in groups[event_id]:
            if item is not representative:
                ledger[int(item["ledger_index"])][
                    "selection_reason_code"
                ] = "not_deterministic_event_representative"

    clob_valid: list[dict[str, Any]] = []
    clob_receipts: list[dict[str, object]] = []
    for item in representatives:
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
        midpoint, midpoint_reasons = _midpoint_value(midpoint_response)
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
        item = dict(item)
        item.update(
            {
                "best_bid": bid,
                "best_ask": ask,
                "market_probability": midpoint,
                "spread": spread,
                "market_price_timestamp": midpoint_response.acquired_at,
                "clob_receipts": frozen,
                "cohort_rank": base._rank(SELECTION_SEED, item["event_id"]),
            }
        )
        clob_valid.append(item)

    selected = sorted(clob_valid, key=lambda item: str(item["cohort_rank"]))[
        :TARGET_COHORT
    ]
    selected_ids = {str(item["market_id"]) for item in selected}
    for entry in ledger:
        if str(entry.get("market_id")) in selected_ids:
            entry["selected"] = True
            entry["selection_reason_code"] = "selected_by_frozen_event_rank"
        elif entry.get("event_representative") and entry.get("clob_status") == "valid":
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
        if entry.get("event_representative"):
            reason_counts.update(entry.get("clob_reason_codes") or [])

    summary: dict[str, object] = {
        "schema_version": 2,
        "purpose": PURPOSE,
        "protocol_commit": PROTOCOL_COMMIT,
        "code_commit": code_commit,
        "selection_seed": SELECTION_SEED,
        "pagination_mode": "gamma-markets-keyset-after_cursor",
        "keyset_max_pages": MAX_PAGES,
        "snapshot_reference_at": base._iso_z(reference),
        "scheduled_end_min": base._iso_z(earliest_end),
        "scheduled_end_max": base._iso_z(latest_end),
        "gamma_pages": len(page_receipts),
        "universe_rows": len(universe),
        "structurally_eligible_markets": sum(
            bool(entry["structural_eligible"]) for entry in ledger
        ),
        "event_representatives": len(representatives),
        "clob_valid_event_representatives": sum(
            entry["clob_status"] == "valid" for entry in ledger
        ),
        "clob_transport_failures": sum(
            entry["clob_status"] == "transport_failure" for entry in ledger
        ),
        "clob_rejection_reason_counts": dict(sorted(reason_counts.items())),
        "selected_rows": len(selected_rows),
        "selected_event_groups": len({row["event_id"] for row in selected_rows}),
        "target_cohort": TARGET_COHORT,
        "adequacy_floor": ADEQUACY_FLOOR,
        "custody_adequate_for_forecaster_preregistration": len(selected_rows)
        >= ADEQUACY_FLOOR,
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
        summary = collect_prospective_custody_v02(
            client,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
        )

    safe_keys = (
        "snapshot_reference_at",
        "gamma_pages",
        "universe_rows",
        "structurally_eligible_markets",
        "event_representatives",
        "clob_valid_event_representatives",
        "clob_transport_failures",
        "clob_rejection_reason_counts",
        "selected_rows",
        "selected_event_groups",
        "custody_adequate_for_forecaster_preregistration",
        "universe_sha256",
        "selection_ledger_sha256",
        "cohort_sha256",
    )
    print(json.dumps({key: summary[key] for key in safe_keys}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
