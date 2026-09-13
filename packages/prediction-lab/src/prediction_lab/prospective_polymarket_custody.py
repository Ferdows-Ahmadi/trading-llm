"""Custody-first one-time prospective Polymarket development cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

PROTOCOL_COMMIT = "1562a16f835f1b75f878341146fa7a867f2439e5"
SELECTION_SEED = "prospective-development-custody-v0.1-selection-seed-2026-09-13"
GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
PAGE_SIZE = 100
MAX_PAGES = 100
TARGET_COHORT = 100
ADEQUACY_FLOOR = 60
MIN_HORIZON = pd.Timedelta(days=7)
MAX_HORIZON = pd.Timedelta(days=45)
MIN_VOLUME = 5000.0
MIN_LIQUIDITY = 1000.0
MAX_SPREAD = 0.10
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


class ProspectiveCustodyError(RuntimeError):
    """Raised when the prospective custody contract cannot be satisfied."""


@dataclass(frozen=True)
class FrozenResponse:
    payload: object
    raw: bytes
    acquired_at: str
    url: str
    params: dict[str, object]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _utc(value: object, *, field: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ProspectiveCustodyError(f"Invalid {field}: {value!r}") from exc
    if pd.isna(timestamp):
        raise ProspectiveCustodyError(f"Missing {field}")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _iso_z(value: pd.Timestamp) -> str:
    return value.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _text(value: object) -> str:
    return str(value or "").strip()


def _rank(*parts: object) -> str:
    joined = "|".join(str(part) for part in parts)
    return _sha256(joined.encode("utf-8"))


def _parent_event(market: dict[str, Any]) -> dict[str, Any] | None:
    events = market.get("events")
    if not isinstance(events, list):
        return None
    candidates = [
        item
        for item in events
        if isinstance(item, dict) and _text(item.get("id"))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: _text(item.get("id")))


def _resolution_sources(
    market: dict[str, Any],
    event: dict[str, Any] | None,
) -> list[str]:
    values = [_text(market.get("resolutionSource"))]
    if event is not None:
        values.append(_text(event.get("resolutionSource")))
    return list(dict.fromkeys(value for value in values if value))


def _binary_tokens(market: dict[str, Any]) -> tuple[str, str] | None:
    outcomes = [_text(item).lower() for item in _json_list(market.get("outcomes"))]
    tokens = [_text(item) for item in _json_list(market.get("clobTokenIds"))]
    if len(outcomes) != 2 or set(outcomes) != {"yes", "no"}:
        return None
    if len(tokens) != 2 or not all(tokens):
        return None
    return tokens[outcomes.index("yes")], tokens[outcomes.index("no")]


def structural_check(
    market: dict[str, Any],
    *,
    earliest_end: pd.Timestamp,
    latest_end: pd.Timestamp,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Apply only preregistered market-structure filters."""
    reasons: list[str] = []
    market_id = _text(market.get("id"))
    condition_id = _text(market.get("conditionId"))
    question = _text(market.get("question"))
    raw_end = market.get("endDate")
    if not market_id:
        reasons.append("missing_market_id")
    if not condition_id:
        reasons.append("missing_condition_id")
    if not question:
        reasons.append("missing_question")
    if not raw_end:
        reasons.append("missing_end_date")

    end_at: pd.Timestamp | None = None
    if raw_end:
        try:
            end_at = _utc(raw_end, field="endDate")
        except ProspectiveCustodyError:
            reasons.append("invalid_end_date")
    if end_at is not None and not earliest_end <= end_at <= latest_end:
        reasons.append("outside_scheduled_horizon")

    if market.get("closed") is not False:
        reasons.append("not_open")
    if market.get("active") is False:
        reasons.append("explicitly_inactive")
    if market.get("enableOrderBook") is not True:
        reasons.append("orderbook_disabled")
    if market.get("acceptingOrders") is not True:
        reasons.append("not_accepting_orders")

    tokens = _binary_tokens(market)
    if tokens is None:
        reasons.append("not_binary_yes_no_with_two_tokens")

    event = _parent_event(market)
    if event is None:
        reasons.append("missing_parent_event")

    volume = _number(market.get("volumeNum"))
    liquidity = _number(market.get("liquidityNum"))
    if volume is None or volume < MIN_VOLUME:
        reasons.append("volume_below_minimum")
    if liquidity is None or liquidity < MIN_LIQUIDITY:
        reasons.append("liquidity_below_minimum")

    description = _text(market.get("description"))
    if not description:
        reasons.append("missing_contract_description")
    sources = _resolution_sources(market, event)
    if not sources:
        reasons.append("missing_resolution_source")

    if reasons:
        return None, reasons
    assert event is not None
    assert end_at is not None
    assert tokens is not None
    assert volume is not None
    assert liquidity is not None
    yes_token, no_token = tokens
    return {
        "market_id": market_id,
        "condition_id": condition_id,
        "event_id": _text(event["id"]),
        "market_slug": _text(market.get("slug")),
        "event_slug": _text(event.get("slug")),
        "question_text": question,
        "description": description,
        "resolution_sources": sources,
        "category": _text(market.get("category")) or "unknown",
        "scheduled_end_at": _iso_z(end_at),
        "volume_num": volume,
        "liquidity_num": liquidity,
        "yes_token_id": yes_token,
        "no_token_id": no_token,
    }, []


class ProspectivePolymarketClient:
    """Small public Gamma/CLOB acquisition boundary with frozen raw responses."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        retries: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ProspectivePolymarketClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(
        self,
        url: str,
        *,
        params: dict[str, object],
    ) -> FrozenResponse:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    raise ProspectiveCustodyError(
                        f"HTTP {response.status_code} from {url}: {response.text[:160]}"
                    )
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ProspectiveCustodyError(
                        f"Non-JSON response from {url}"
                    ) from exc
                return FrozenResponse(
                    payload=payload,
                    raw=response.content,
                    acquired_at=datetime.now(UTC).isoformat(),
                    url=str(response.request.url),
                    params=dict(params),
                )
            except (httpx.HTTPError, ProspectiveCustodyError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise ProspectiveCustodyError(f"Request failed for {url}: {last_error}")

    def gamma_markets_page(self, params: dict[str, object]) -> FrozenResponse:
        return self._get(f"{GAMMA_URL}/markets", params=params)

    def clob_price(self, token_id: str, side: str) -> FrozenResponse:
        return self._get(
            f"{CLOB_URL}/price",
            params={"token_id": token_id, "side": side},
        )

    def clob_midpoint(self, token_id: str) -> FrozenResponse:
        return self._get(
            f"{CLOB_URL}/midpoint",
            params={"token_id": token_id},
        )


def _safe_market_name(market_id: str) -> str:
    cleaned = _SAFE_NAME.sub("_", market_id).strip("._")
    return cleaned[:80] or _sha256(market_id.encode())[:20]


def _freeze_response(path: Path, response: FrozenResponse) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.raw)
    return {
        "file": path.as_posix(),
        "sha256": _sha256(response.raw),
        "acquired_at": response.acquired_at,
        "url": response.url,
        "params": response.params,
    }


def _extract_price(response: FrozenResponse, field: str) -> float | None:
    if not isinstance(response.payload, dict):
        return None
    return _number(response.payload.get(field))


def _contract_object(item: dict[str, Any]) -> dict[str, object]:
    return {
        "market_id": item["market_id"],
        "condition_id": item["condition_id"],
        "event_id": item["event_id"],
        "market_slug": item["market_slug"],
        "event_slug": item["event_slug"],
        "question_text": item["question_text"],
        "description": item["description"],
        "resolution_sources": item["resolution_sources"],
        "yes_token_id": item["yes_token_id"],
        "no_token_id": item["no_token_id"],
        "scheduled_end_at": item["scheduled_end_at"],
    }


def collect_prospective_custody(
    client: ProspectivePolymarketClient,
    *,
    output_directory: Path,
    code_commit: str,
    snapshot_reference_at: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    """Run the preregistered one-time custody acquisition without model inference."""
    if output_directory.exists():
        raise ProspectiveCustodyError("Refusing to replace existing custody output")
    output_directory.mkdir(parents=True)
    raw_gamma = output_directory / "raw" / "gamma"
    raw_clob = output_directory / "raw" / "clob"

    reference = (
        _utc(snapshot_reference_at, field="snapshot_reference_at")
        if snapshot_reference_at is not None
        else pd.Timestamp.now(tz="UTC")
    )
    earliest_end = reference + MIN_HORIZON
    latest_end = reference + MAX_HORIZON

    universe: list[dict[str, Any]] = []
    page_receipts: list[dict[str, object]] = []
    completed = False
    for page_index in range(MAX_PAGES):
        params: dict[str, object] = {
            "closed": "false",
            "end_date_min": _iso_z(earliest_end),
            "end_date_max": _iso_z(latest_end),
            "order": "id",
            "ascending": "true",
            "limit": PAGE_SIZE,
            "offset": page_index * PAGE_SIZE,
        }
        response = client.gamma_markets_page(params)
        if not isinstance(response.payload, list):
            raise ProspectiveCustodyError("Gamma /markets response must be a list")
        path = raw_gamma / f"page-{page_index:03d}.json"
        receipt = _freeze_response(path, response)
        receipt["page_index"] = page_index
        receipt["row_count"] = len(response.payload)
        page_receipts.append(receipt)
        for market in response.payload:
            if isinstance(market, dict):
                universe.append(market)
        if len(response.payload) < PAGE_SIZE:
            completed = True
            break
    if not completed:
        raise ProspectiveCustodyError("Gamma pagination hit 100-page safety limit")

    ledger: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    seen_market_ids: set[str] = set()
    for index, market in enumerate(universe):
        market_id = _text(market.get("id"))
        if market_id and market_id in seen_market_ids:
            raise ProspectiveCustodyError(f"Duplicate market ID in universe: {market_id}")
        if market_id:
            seen_market_ids.add(market_id)
        normalized, reasons = structural_check(
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
                    "event_rank": _rank(
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
            key=lambda item: _rank(
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
        safe = _safe_market_name(market_id)
        try:
            bid_response = client.clob_price(yes_token, "BUY")
            ask_response = client.clob_price(yes_token, "SELL")
            midpoint_response = client.clob_midpoint(yes_token)
        except ProspectiveCustodyError as exc:
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
            receipt = _freeze_response(raw_clob / f"{safe}-{label}.json", response)
            receipt.update({"market_id": market_id, "kind": label})
            clob_receipts.append(receipt)
            frozen[label] = receipt

        bid = _extract_price(bid_response, "price")
        ask = _extract_price(ask_response, "price")
        midpoint = _extract_price(midpoint_response, "mid_price")
        reasons: list[str] = []
        values = (bid, ask, midpoint)
        if any(value is None or not 0.0 < value < 1.0 for value in values):
            reasons.append("invalid_clob_price")
        spread: float | None = None
        if not reasons:
            assert bid is not None and ask is not None and midpoint is not None
            spread = ask - bid
            if not bid <= midpoint <= ask:
                reasons.append("midpoint_outside_bid_ask")
            if spread < 0:
                reasons.append("negative_spread")
            elif spread > MAX_SPREAD:
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
                "cohort_rank": _rank(SELECTION_SEED, item["event_id"]),
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
        contract = _contract_object(item)
        selected_rows.append(
            {
                **contract,
                "category": item["category"],
                "volume_num": item["volume_num"],
                "liquidity_num": item["liquidity_num"],
                "snapshot_reference_at": _iso_z(reference),
                "source_cutoff_at": _iso_z(reference),
                "market_price_timestamp": item["market_price_timestamp"],
                "market_probability": item["market_probability"],
                "best_bid": item["best_bid"],
                "best_ask": item["best_ask"],
                "spread": item["spread"],
                "cohort_rank": item["cohort_rank"],
                "contract_sha256": _sha256(_canonical_bytes(contract)),
            }
        )

    universe_path = output_directory / "universe-markets.jsonl"
    universe_payload = b"".join(
        _canonical_bytes(market) + b"\n" for market in universe
    )
    universe_path.write_bytes(universe_payload)
    ledger_path = output_directory / "selection-ledger.jsonl"
    ledger_payload = b"".join(_canonical_bytes(row) + b"\n" for row in ledger)
    ledger_path.write_bytes(ledger_payload)
    cohort_path = output_directory / "cohort.jsonl"
    cohort_payload = b"".join(
        _canonical_bytes(row) + b"\n" for row in selected_rows
    )
    cohort_path.write_bytes(cohort_payload)

    receipts = {
        "gamma_pages": page_receipts,
        "clob_responses": clob_receipts,
    }
    receipts_path = output_directory / "acquisition-receipts.json"
    receipts_path.write_bytes(_canonical_bytes(receipts) + b"\n")

    structurally_eligible = sum(
        bool(entry["structural_eligible"]) for entry in ledger
    )
    clob_valid_count = sum(entry["clob_status"] == "valid" for entry in ledger)
    transport_failures = sum(
        entry["clob_status"] == "transport_failure" for entry in ledger
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "purpose": "prospective-development-custody-v0.1",
        "protocol_commit": PROTOCOL_COMMIT,
        "code_commit": code_commit,
        "selection_seed": SELECTION_SEED,
        "snapshot_reference_at": _iso_z(reference),
        "scheduled_end_min": _iso_z(earliest_end),
        "scheduled_end_max": _iso_z(latest_end),
        "gamma_pages": len(page_receipts),
        "universe_rows": len(universe),
        "structurally_eligible_markets": structurally_eligible,
        "event_representatives": len(representatives),
        "clob_valid_event_representatives": clob_valid_count,
        "clob_transport_failures": transport_failures,
        "selected_rows": len(selected_rows),
        "selected_event_groups": len({row["event_id"] for row in selected_rows}),
        "target_cohort": TARGET_COHORT,
        "adequacy_floor": ADEQUACY_FLOOR,
        "custody_adequate_for_forecaster_preregistration": len(selected_rows)
        >= ADEQUACY_FLOOR,
        "minimum_volume": MIN_VOLUME,
        "minimum_liquidity": MIN_LIQUIDITY,
        "maximum_spread": MAX_SPREAD,
        "universe_sha256": _sha256(universe_payload),
        "selection_ledger_sha256": _sha256(ledger_payload),
        "cohort_sha256": _sha256(cohort_payload),
        "acquisition_receipts_sha256": _sha256(receipts_path.read_bytes()),
        "forecaster_run": False,
        "model_score_computed": False,
        "reserved_holdout_accessed": False,
    }
    summary_path = output_directory / "custody-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    with ProspectivePolymarketClient() as client:
        summary = collect_prospective_custody(
            client,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
        )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "snapshot_reference_at",
                    "gamma_pages",
                    "universe_rows",
                    "structurally_eligible_markets",
                    "event_representatives",
                    "clob_valid_event_representatives",
                    "clob_transport_failures",
                    "selected_rows",
                    "selected_event_groups",
                    "custody_adequate_for_forecaster_preregistration",
                    "universe_sha256",
                    "selection_ledger_sha256",
                    "cohort_sha256",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
