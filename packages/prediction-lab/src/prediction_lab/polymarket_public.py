from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np
import pandas as pd

from prediction_lab.cases import normalize_case_frame

POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com"
POLYMARKET_DATA_URL = "https://data-api.polymarket.com"


class PolymarketPublicAPIError(RuntimeError):
    """Raised when public Polymarket data cannot be acquired safely."""


@dataclass(frozen=True)
class PolymarketAcquisition:
    acquired_at: str
    candidate_markets: int
    attempted_markets: int
    usable_cases: int
    minimum_lead: str
    maximum_price_staleness: str
    minimum_volume: float
    market_pages: int
    api_gamma_url: str
    api_data_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_timestamp(value: object, *, field: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise PolymarketPublicAPIError(f"Invalid {field} timestamp: {value!r}") from exc
    if pd.isna(timestamp):
        raise PolymarketPublicAPIError(f"Missing {field} timestamp")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


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


def _resolved_binary_outcome(market: dict[str, Any]) -> int | None:
    outcomes = [str(value).strip().lower() for value in _json_list(market.get("outcomes"))]
    try:
        prices = [float(value) for value in _json_list(market.get("outcomePrices"))]
    except (TypeError, ValueError):
        return None

    if len(outcomes) != 2 or set(outcomes) != {"yes", "no"} or len(prices) != 2:
        return None
    yes_index = outcomes.index("yes")
    no_index = outcomes.index("no")
    if prices[yes_index] >= 0.99 and prices[no_index] <= 0.01:
        return 1
    if prices[yes_index] <= 0.01 and prices[no_index] >= 0.99:
        return 0
    return None


def _volume(market: dict[str, Any]) -> float:
    value = market.get("volumeNum", market.get("volume", 0.0))
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _actual_lifetime(market: dict[str, Any]) -> pd.Timedelta | None:
    start_value = market.get("startDate") or market.get("createdAt")
    close_value = market.get("closedTime")
    if not start_value or not close_value:
        return None
    try:
        start = _utc_timestamp(start_value, field="startDate")
        closed = _utc_timestamp(close_value, field="closedTime")
    except PolymarketPublicAPIError:
        return None
    lifetime = closed - start
    return lifetime if lifetime > pd.Timedelta(0) else None


def _event_id(market: dict[str, Any]) -> str:
    events = market.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict) and event.get("id"):
                return f"polymarket-event:{event['id']}"
    condition_id = str(market.get("conditionId") or market.get("id") or "").strip()
    if not condition_id:
        raise PolymarketPublicAPIError("Cannot derive event group for market")
    return f"polymarket-market:{condition_id}"


def _is_candidate(
    market: dict[str, Any],
    *,
    minimum_volume: float,
    minimum_lifetime: pd.Timedelta,
) -> bool:
    lifetime = _actual_lifetime(market)
    return (
        bool(market.get("id"))
        and bool(market.get("conditionId"))
        and bool(market.get("question"))
        and bool(market.get("closed"))
        and lifetime is not None
        and lifetime >= minimum_lifetime
        and _volume(market) >= minimum_volume
        and _resolved_binary_outcome(market) is not None
    )


def _close_sort_key(market: dict[str, Any]) -> pd.Timestamp:
    return _utc_timestamp(market["closedTime"], field="closedTime")


def _prioritize_markets(
    markets: list[dict[str, Any]],
    *,
    target_questions: int,
) -> list[dict[str, Any]]:
    ordered = sorted(markets, key=_close_sort_key)
    if len(ordered) <= target_questions * 2:
        return ordered
    primary_count = min(len(ordered), target_questions * 2)
    positions = np.linspace(0, len(ordered) - 1, num=primary_count, dtype=int)
    primary_indices = list(dict.fromkeys(int(position) for position in positions))
    selected = set(primary_indices)
    remaining = [index for index in range(len(ordered)) if index not in selected]
    return [ordered[index] for index in [*primary_indices, *remaining]]


class PolymarketPublicClient:
    """Unauthenticated Gamma + Data API client for resolved benchmark construction."""

    def __init__(
        self,
        *,
        gamma_url: str = POLYMARKET_GAMMA_URL,
        data_url: str = POLYMARKET_DATA_URL,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        retries: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        self.gamma_url = gamma_url.rstrip("/")
        self.data_url = data_url.rstrip("/")
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> PolymarketPublicClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_json(
        self,
        base_url: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
    ) -> object:
        url = f"{base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    raise PolymarketPublicAPIError(
                        f"Polymarket returned HTTP {response.status_code} for {path}: "
                        f"{response.text[:200]}"
                    )
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise PolymarketPublicAPIError(f"Polymarket request failed for {path}: {last_error}")

    def fetch_candidate_markets(
        self,
        *,
        minimum_volume: float,
        minimum_lifetime: pd.Timedelta,
        target_items: int,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Page through closed Gamma markets and retain resolved long-duration binaries."""
        if target_items < 1:
            raise ValueError("target_items must be positive")
        if minimum_lifetime <= pd.Timedelta(0):
            raise ValueError("minimum_lifetime must be positive")

        candidates: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        for _ in range(max_pages):
            params: dict[str, object] = {
                "limit": 100,
                "closed": "true",
                "order": "endDate",
                "ascending": "false",
            }
            if cursor:
                params["after_cursor"] = cursor
            payload = self._get_json(self.gamma_url, "/markets/keyset", params=params)
            if not isinstance(payload, dict):
                raise PolymarketPublicAPIError("Gamma keyset response must be an object")
            markets = payload.get("markets", [])
            if not isinstance(markets, list):
                raise PolymarketPublicAPIError("Gamma 'markets' field must be a list")

            for market in markets:
                if not isinstance(market, dict):
                    continue
                if not _is_candidate(
                    market,
                    minimum_volume=minimum_volume,
                    minimum_lifetime=minimum_lifetime,
                ):
                    continue
                condition_id = str(market["conditionId"])
                existing = candidates.get(condition_id)
                if existing is None or _close_sort_key(market) > _close_sort_key(existing):
                    candidates[condition_id] = market

            if len(candidates) >= target_items:
                break
            next_cursor = payload.get("next_cursor")
            cursor = str(next_cursor) if next_cursor else None
            if not cursor:
                break

        return _prioritize_markets(
            list(candidates.values()),
            target_questions=min(target_items, len(candidates)),
        )[:target_items]

    def latest_trade_before(
        self,
        *,
        condition_id: str,
        target: pd.Timestamp,
    ) -> dict[str, Any] | None:
        """Find a recent trade at or before target using progressively wider windows."""
        target = _utc_timestamp(target, field="target")
        for lookback in ("1D", "7D", "30D", "180D", "730D"):
            start = target - pd.Timedelta(lookback)
            payload = self._get_json(
                self.data_url,
                "/trades",
                params={
                    "market": condition_id,
                    "start": int(start.timestamp()),
                    "end": int(target.timestamp()),
                    "limit": 10000,
                    "takerOnly": "true",
                },
            )
            if not isinstance(payload, list):
                raise PolymarketPublicAPIError("Data API trades response must be a list")

            eligible: list[dict[str, Any]] = []
            for trade in payload:
                if not isinstance(trade, dict):
                    continue
                if str(trade.get("conditionId", "")) != condition_id:
                    continue
                try:
                    timestamp = int(trade.get("timestamp", 0))
                except (TypeError, ValueError):
                    continue
                if timestamp <= int(target.timestamp()):
                    eligible.append(trade)
            if eligible:
                return max(eligible, key=lambda trade: int(trade["timestamp"]))
        return None


def _yes_probability_from_trade(trade: dict[str, Any]) -> float | None:
    try:
        price = float(trade.get("price"))
    except (TypeError, ValueError):
        return None
    if not 0.0 < price < 1.0:
        return None

    outcome = str(trade.get("outcome", "")).strip().lower()
    if outcome == "yes":
        return price
    if outcome == "no":
        return 1.0 - price
    return None


def collect_public_polymarket_cases(
    client: PolymarketPublicClient,
    *,
    max_questions: int = 300,
    candidate_multiplier: int = 3,
    minimum_lead: str | pd.Timedelta = "7D",
    maximum_price_staleness: str | pd.Timedelta = "3D",
    minimum_volume: float = 100.0,
    max_market_pages: int = 12,
) -> tuple[
    pd.DataFrame,
    PolymarketAcquisition,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Build a fixed-lead benchmark from public Polymarket APIs."""
    if max_questions < 4:
        raise ValueError("max_questions must be at least 4")
    if candidate_multiplier < 1:
        raise ValueError("candidate_multiplier must be positive")

    lead = pd.Timedelta(minimum_lead)
    staleness_limit = pd.Timedelta(maximum_price_staleness)
    if lead <= pd.Timedelta(0):
        raise ValueError("minimum_lead must be positive")
    if staleness_limit <= pd.Timedelta(0):
        raise ValueError("maximum_price_staleness must be positive")

    candidates = client.fetch_candidate_markets(
        minimum_volume=minimum_volume,
        minimum_lifetime=lead,
        target_items=max_questions * candidate_multiplier,
        max_pages=max_market_pages,
    )
    candidates = _prioritize_markets(candidates, target_questions=max_questions)

    rows: list[dict[str, Any]] = []
    markets_used: list[dict[str, Any]] = []
    trades_used: list[dict[str, Any]] = []
    attempted = 0

    for market in candidates:
        if len(rows) >= max_questions:
            break
        attempted += 1
        actual_close = _utc_timestamp(market["closedTime"], field="closedTime")
        target = actual_close - lead
        trade = client.latest_trade_before(
            condition_id=str(market["conditionId"]),
            target=target,
        )
        if trade is None:
            continue

        probability = _yes_probability_from_trade(trade)
        outcome = _resolved_binary_outcome(market)
        if probability is None or outcome is None:
            continue

        forecasted_at = pd.Timestamp(int(trade["timestamp"]), unit="s", tz="UTC")
        snapshot_staleness = target - forecasted_at
        if forecasted_at > target or actual_close <= forecasted_at:
            continue
        if snapshot_staleness > staleness_limit:
            continue

        rows.append(
            {
                "question_id": str(market["id"]),
                "question_text": str(market["question"]),
                "forecasted_at": forecasted_at,
                "resolved_at": actual_close,
                "market_price_timestamp": forecasted_at,
                "source_cutoff_at": forecasted_at,
                "market_probability": probability,
                "outcome": outcome,
                "category": str(market.get("category") or "unknown"),
                "platform": "polymarket",
                "event_id": _event_id(market),
                "snapshot_staleness_hours": snapshot_staleness.total_seconds() / 3600.0,
            }
        )
        markets_used.append(market)
        trades_used.append(trade)

    if len(rows) < 4:
        raise PolymarketPublicAPIError(
            f"Only {len(rows)} usable cases were collected from "
            f"{len(candidates)} candidates ({attempted} attempted)"
        )

    cases = normalize_case_frame(pd.DataFrame(rows))
    cases.sort_values(["forecasted_at", "question_id"], inplace=True)
    cases.drop_duplicates("question_id", keep="last", inplace=True)
    cases.reset_index(drop=True, inplace=True)

    acquisition = PolymarketAcquisition(
        acquired_at=datetime.now(UTC).isoformat(),
        candidate_markets=len(candidates),
        attempted_markets=attempted,
        usable_cases=len(cases),
        minimum_lead=str(lead),
        maximum_price_staleness=str(staleness_limit),
        minimum_volume=minimum_volume,
        market_pages=max_market_pages,
        api_gamma_url=client.gamma_url,
        api_data_url=client.data_url,
    )
    return cases, acquisition, markets_used, trades_used
