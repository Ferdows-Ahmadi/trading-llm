from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np
import pandas as pd

from prediction_lab.cases import normalize_case_frame

KALSHI_API_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"


class KalshiPublicAPIError(RuntimeError):
    """Raised when public Kalshi data cannot be acquired safely."""


@dataclass(frozen=True)
class KalshiCutoffs:
    market_settled_at: pd.Timestamp
    trades_created_at: pd.Timestamp

    def to_dict(self) -> dict[str, str]:
        return {
            "market_settled_at": self.market_settled_at.isoformat(),
            "trades_created_at": self.trades_created_at.isoformat(),
        }


@dataclass(frozen=True)
class KalshiAcquisition:
    acquired_at: str
    cutoffs: dict[str, str]
    candidate_markets: int
    attempted_markets: int
    usable_cases: int
    minimum_lead: str
    minimum_volume: int
    market_pages: int
    max_trade_pages: int
    api_base_url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_timestamp(value: object, *, field: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise KalshiPublicAPIError(f"Invalid {field} timestamp: {value!r}") from exc
    if pd.isna(timestamp):
        raise KalshiPublicAPIError(f"Missing {field} timestamp")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _volume(market: dict[str, Any]) -> float:
    value = market.get("volume_fp", market.get("volume", 0))
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_usable_market(market: dict[str, Any], *, minimum_volume: int) -> bool:
    result = str(market.get("result", "")).lower()
    market_type = str(market.get("market_type", "binary")).lower()
    return (
        bool(market.get("ticker"))
        and bool(market.get("title"))
        and market_type == "binary"
        and result in {"yes", "no"}
        and bool(market.get("close_time"))
        and _volume(market) >= minimum_volume
        and not bool(market.get("is_provisional", False))
    )


def _market_sort_time(market: dict[str, Any]) -> pd.Timestamp:
    for field in ("settlement_ts", "close_time", "expiration_time"):
        if market.get(field):
            return _utc_timestamp(market[field], field=field)
    return pd.Timestamp.min.tz_localize("UTC")


def _prioritize_markets(
    markets: list[dict[str, Any]],
    *,
    target_questions: int,
) -> list[dict[str, Any]]:
    """Spread early trade lookups across the candidate time range."""
    ordered = sorted(markets, key=_market_sort_time)
    if len(ordered) <= target_questions * 2:
        return ordered

    primary_count = min(len(ordered), target_questions * 2)
    primary_positions = np.linspace(0, len(ordered) - 1, num=primary_count, dtype=int)
    primary_indices = list(dict.fromkeys(int(index) for index in primary_positions))
    selected = set(primary_indices)
    remaining_indices = [index for index in range(len(ordered)) if index not in selected]
    return [ordered[index] for index in [*primary_indices, *remaining_indices]]


class KalshiPublicClient:
    """Small unauthenticated client for public market and trade history."""

    def __init__(
        self,
        *,
        base_url: str = KALSHI_API_BASE_URL,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20.0,
        retries: int = 3,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> KalshiPublicClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_json(self, path: str, *, params: dict[str, object] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    raise KalshiPublicAPIError(
                        f"Kalshi returned HTTP {response.status_code} for {path}: "
                        f"{response.text[:200]}"
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise KalshiPublicAPIError(f"Kalshi returned non-object JSON for {path}")
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(self.retry_backoff_seconds * (2**attempt))

        raise KalshiPublicAPIError(f"Kalshi request failed for {path}: {last_error}")

    def get_cutoffs(self) -> KalshiCutoffs:
        payload = self._get_json("/historical/cutoff")
        return KalshiCutoffs(
            market_settled_at=_utc_timestamp(
                payload.get("market_settled_ts"), field="market_settled_ts"
            ),
            trades_created_at=_utc_timestamp(
                payload.get("trades_created_ts"), field="trades_created_ts"
            ),
        )

    def _paged_items(
        self,
        path: str,
        *,
        key: str,
        params: dict[str, object],
        max_pages: int,
        max_items: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(max_pages):
            page_params = dict(params)
            if cursor:
                page_params["cursor"] = cursor
            payload = self._get_json(path, params=page_params)
            page = payload.get(key, [])
            if not isinstance(page, list):
                raise KalshiPublicAPIError(f"Kalshi field {key!r} is not a list")
            items.extend(item for item in page if isinstance(item, dict))
            if len(items) >= max_items:
                return items[:max_items]
            cursor_value = payload.get("cursor")
            cursor = str(cursor_value) if cursor_value else None
            if not cursor:
                break
        return items[:max_items]

    def fetch_candidate_markets(
        self,
        *,
        minimum_volume: int,
        max_items: int,
        max_pages: int = 8,
    ) -> list[dict[str, Any]]:
        """Collect recent settled markets, then archived markets if more are needed."""
        if max_items < 1:
            raise ValueError("max_items must be positive")

        recent = self._paged_items(
            "/markets",
            key="markets",
            params={"limit": 1000, "status": "settled", "mve_filter": "exclude"},
            max_pages=max_pages,
            max_items=max_items,
        )
        combined = recent
        if len(combined) < max_items:
            historical = self._paged_items(
                "/historical/markets",
                key="markets",
                params={"limit": 1000, "mve_filter": "exclude"},
                max_pages=max_pages,
                max_items=max_items - len(combined),
            )
            combined = [*combined, *historical]

        by_ticker: dict[str, dict[str, Any]] = {}
        for market in combined:
            ticker = str(market.get("ticker", ""))
            if not ticker or not _is_usable_market(market, minimum_volume=minimum_volume):
                continue
            existing = by_ticker.get(ticker)
            if existing is None or _market_sort_time(market) > _market_sort_time(existing):
                by_ticker[ticker] = market
        return sorted(by_ticker.values(), key=_market_sort_time)

    def _trades_from_endpoint(
        self,
        path: str,
        *,
        ticker: str,
        max_timestamp: pd.Timestamp,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        return self._paged_items(
            path,
            key="trades",
            params={
                "ticker": ticker,
                "max_ts": int(max_timestamp.timestamp()),
                "limit": 1000,
            },
            max_pages=max_pages,
            max_items=max_pages * 1000,
        )

    def latest_trade_before(
        self,
        *,
        ticker: str,
        target: pd.Timestamp,
        trades_cutoff: pd.Timestamp,
        max_pages: int = 3,
    ) -> dict[str, Any] | None:
        """Return the latest public trade at or before target across live/archive tiers."""
        target = _utc_timestamp(target, field="target")
        trades_cutoff = _utc_timestamp(trades_cutoff, field="trades_cutoff")

        endpoint_queries: list[tuple[str, pd.Timestamp]] = []
        if target >= trades_cutoff:
            endpoint_queries.append(("/markets/trades", target))
            historical_target = min(target, trades_cutoff - pd.Timedelta(seconds=1))
            endpoint_queries.append(("/historical/trades", historical_target))
        else:
            endpoint_queries.append(("/historical/trades", target))

        candidates: list[dict[str, Any]] = []
        for path, endpoint_target in endpoint_queries:
            trades = self._trades_from_endpoint(
                path,
                ticker=ticker,
                max_timestamp=endpoint_target,
                max_pages=max_pages,
            )
            for trade in trades:
                if str(trade.get("ticker", "")) != ticker or not trade.get("created_time"):
                    continue
                created = _utc_timestamp(trade["created_time"], field="created_time")
                if created <= target:
                    candidates.append(trade)
            if candidates:
                break

        if not candidates:
            return None
        return max(
            candidates,
            key=lambda trade: _utc_timestamp(trade["created_time"], field="created_time"),
        )


def collect_public_kalshi_cases(
    client: KalshiPublicClient,
    *,
    max_questions: int = 500,
    candidate_multiplier: int = 4,
    minimum_lead: str | pd.Timedelta = "7D",
    minimum_volume: int = 100,
    max_market_pages: int = 8,
    max_trade_pages: int = 3,
) -> tuple[pd.DataFrame, KalshiAcquisition, list[dict[str, Any]], list[dict[str, Any]]]:
    """Build a manageable benchmark directly from Kalshi's public endpoints."""
    if max_questions < 4:
        raise ValueError("max_questions must be at least 4")
    if candidate_multiplier < 1:
        raise ValueError("candidate_multiplier must be positive")

    lead = pd.Timedelta(minimum_lead)
    if lead <= pd.Timedelta(0):
        raise ValueError("minimum_lead must be positive")

    cutoffs = client.get_cutoffs()
    candidates = client.fetch_candidate_markets(
        minimum_volume=minimum_volume,
        max_items=max_questions * candidate_multiplier,
        max_pages=max_market_pages,
    )
    candidates = _prioritize_markets(candidates, target_questions=max_questions)

    case_rows: list[dict[str, Any]] = []
    markets_used: list[dict[str, Any]] = []
    trades_used: list[dict[str, Any]] = []
    attempted = 0

    for market in candidates:
        if len(case_rows) >= max_questions:
            break
        attempted += 1
        ticker = str(market["ticker"])
        close_time = _utc_timestamp(market["close_time"], field="close_time")
        target = close_time - lead
        trade = client.latest_trade_before(
            ticker=ticker,
            target=target,
            trades_cutoff=cutoffs.trades_created_at,
            max_pages=max_trade_pages,
        )
        if trade is None:
            continue

        try:
            probability = float(trade.get("yes_price_dollars"))
        except (TypeError, ValueError):
            continue
        if not 0.0 < probability < 1.0:
            continue

        forecasted_at = _utc_timestamp(trade["created_time"], field="created_time")
        resolution_value = market.get("settlement_ts") or market.get("close_time")
        resolved_at = _utc_timestamp(resolution_value, field="resolution")
        if resolved_at <= forecasted_at:
            continue

        result = str(market["result"]).lower()
        case_rows.append(
            {
                "question_id": ticker,
                "question_text": str(market["title"]),
                "forecasted_at": forecasted_at,
                "resolved_at": resolved_at,
                "market_price_timestamp": forecasted_at,
                "source_cutoff_at": forecasted_at,
                "market_probability": probability,
                "outcome": 1 if result == "yes" else 0,
                "category": "unknown",
                "platform": "kalshi",
            }
        )
        markets_used.append(market)
        trades_used.append(trade)

    if len(case_rows) < 4:
        raise KalshiPublicAPIError(
            f"Only {len(case_rows)} usable cases were collected from {attempted} attempts"
        )

    cases = normalize_case_frame(pd.DataFrame(case_rows))
    cases.sort_values(["forecasted_at", "question_id"], inplace=True)
    cases.reset_index(drop=True, inplace=True)

    acquisition = KalshiAcquisition(
        acquired_at=datetime.now(UTC).isoformat(),
        cutoffs=cutoffs.to_dict(),
        candidate_markets=len(candidates),
        attempted_markets=attempted,
        usable_cases=len(cases),
        minimum_lead=str(lead),
        minimum_volume=minimum_volume,
        market_pages=max_market_pages,
        max_trade_pages=max_trade_pages,
        api_base_url=client.base_url,
    )
    return cases, acquisition, markets_used, trades_used
