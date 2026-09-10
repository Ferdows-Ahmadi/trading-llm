from __future__ import annotations

import json
from collections.abc import Iterable

import numpy as np
import pandas as pd

from prediction_lab.cases import normalize_case_frame

_CASE_COLUMNS = [
    "question_id",
    "question_text",
    "forecasted_at",
    "resolved_at",
    "market_price_timestamp",
    "source_cutoff_at",
    "market_probability",
    "outcome",
    "category",
    "platform",
]


class JonBeckerAdapterError(ValueError):
    """Raised when upstream prediction-market-analysis data is incompatible."""


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], *, label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise JonBeckerAdapterError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _empty_cases() -> pd.DataFrame:
    return pd.DataFrame(columns=_CASE_COLUMNS)


def _json_list(value: object, *, field: str) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        raise JonBeckerAdapterError(f"{field} cannot be null")
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError) as exc:
        raise JonBeckerAdapterError(f"{field} must contain a JSON list") from exc
    if not isinstance(parsed, list):
        raise JonBeckerAdapterError(f"{field} must contain a JSON list")
    return parsed


def _first_available_timestamp(row: pd.Series, columns: tuple[str, ...]) -> object:
    for column in columns:
        if column not in row.index:
            continue
        value = row[column]
        if pd.notna(value):
            return value
    raise JonBeckerAdapterError(
        f"Could not determine resolution-observed timestamp from {', '.join(columns)}"
    )


def _resolution_observed_at(row: pd.Series) -> object:
    # Prefer the market's own close/end boundary. A much later metadata fetch could
    # otherwise make a supposedly seven-day-ahead snapshot much closer to the event.
    return _first_available_timestamp(row, ("close_time", "end_date", "_fetched_at"))


def build_kalshi_trade_cases(
    markets: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    """Create YES-probability forecast cases from finalized Kalshi trades.

    A trade's ``yes_price`` is treated as the contemporaneous market baseline.
    If multiple trades occur at exactly the same timestamp for one question, the
    last upstream row is retained so the evaluator has one snapshot per instant.
    """

    _require_columns(
        markets,
        ("ticker", "title", "status", "result"),
        label="Kalshi markets",
    )
    _require_columns(
        trades,
        ("ticker", "yes_price", "created_time"),
        label="Kalshi trades",
    )

    resolved = markets.loc[
        markets["status"].astype(str).str.lower().eq("finalized")
        & markets["result"].astype(str).str.lower().isin(["yes", "no"])
    ].copy()
    if resolved.empty or trades.empty:
        return _empty_cases()

    resolved["resolved_at"] = resolved.apply(_resolution_observed_at, axis=1)
    resolved["outcome"] = (
        resolved["result"].astype(str).str.lower().eq("yes").astype(int)
    )

    keep = ["ticker", "title", "resolved_at", "outcome"]
    if "event_ticker" in resolved.columns:
        keep.append("event_ticker")
    resolved = resolved[keep].drop_duplicates("ticker", keep="last")

    joined = trades.reset_index(names="_source_order").merge(
        resolved,
        on="ticker",
        how="inner",
        validate="many_to_one",
    )
    if joined.empty:
        return _empty_cases()

    yes_probability = pd.to_numeric(joined["yes_price"], errors="coerce") / 100.0
    valid_price = yes_probability.between(0.0, 1.0, inclusive="both")
    joined = joined.loc[valid_price].copy()
    yes_probability = yes_probability.loc[valid_price]
    if joined.empty:
        return _empty_cases()

    cases = pd.DataFrame(
        {
            "question_id": joined["ticker"].astype(str),
            "question_text": joined["title"].astype(str),
            "forecasted_at": joined["created_time"],
            "resolved_at": joined["resolved_at"],
            "market_price_timestamp": joined["created_time"],
            "source_cutoff_at": joined["created_time"],
            "market_probability": yes_probability.to_numpy(),
            "outcome": joined["outcome"].astype(int),
            "category": "unknown",
            "platform": "kalshi",
            "_source_order": joined["_source_order"].to_numpy(),
        }
    )

    cases["_sort_time"] = pd.to_datetime(cases["forecasted_at"], utc=True, errors="raise")
    cases.sort_values(["question_id", "_sort_time", "_source_order"], inplace=True)
    cases.drop_duplicates(
        subset=["question_id", "_sort_time"],
        keep="last",
        inplace=True,
    )
    cases.drop(columns=["_source_order", "_sort_time"], inplace=True)
    return normalize_case_frame(cases)


def _polymarket_resolution_rows(markets: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        markets,
        ("id", "question", "closed", "outcomes", "outcome_prices", "clob_token_ids"),
        label="Polymarket markets",
    )

    rows: list[dict[str, object]] = []
    for source_order, (_, row) in enumerate(markets.iterrows()):
        if not bool(row["closed"]):
            continue

        try:
            outcomes = [
                str(value).strip().lower()
                for value in _json_list(row["outcomes"], field="outcomes")
            ]
            prices = [
                float(value)
                for value in _json_list(row["outcome_prices"], field="outcome_prices")
            ]
            token_ids = [
                str(value)
                for value in _json_list(row["clob_token_ids"], field="clob_token_ids")
            ]
        except (JonBeckerAdapterError, TypeError, ValueError):
            continue

        if len(outcomes) != 2 or len(prices) != 2 or len(token_ids) != 2:
            continue
        if set(outcomes) != {"yes", "no"}:
            continue

        yes_index = outcomes.index("yes")
        no_index = outcomes.index("no")
        yes_price = prices[yes_index]
        no_price = prices[no_index]

        if yes_price >= 0.99 and no_price <= 0.01:
            outcome = 1
        elif yes_price <= 0.01 and no_price >= 0.99:
            outcome = 0
        else:
            continue

        try:
            resolved_at = _resolution_observed_at(row)
        except JonBeckerAdapterError:
            continue

        rows.append(
            {
                "question_id": str(row["id"]),
                "question_text": str(row["question"]),
                "resolved_at": resolved_at,
                "outcome": outcome,
                "yes_token_id": token_ids[yes_index],
                "no_token_id": token_ids[no_index],
                "_source_order": source_order,
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "question_id",
                "question_text",
                "resolved_at",
                "outcome",
                "yes_token_id",
                "no_token_id",
            ]
        )

    resolved = pd.DataFrame(rows)
    resolved.sort_values("_source_order", inplace=True)
    resolved.drop_duplicates("question_id", keep="last", inplace=True)
    return resolved.drop(columns="_source_order")


def _trade_token_and_price(row: pd.Series) -> tuple[str, float] | None:
    maker_asset = str(row["maker_asset_id"])
    taker_asset = str(row["taker_asset_id"])

    try:
        maker_amount = float(row["maker_amount"])
        taker_amount = float(row["taker_amount"])
    except (TypeError, ValueError):
        return None

    if maker_amount <= 0.0 or taker_amount <= 0.0:
        return None

    if maker_asset == "0" and taker_asset != "0":
        return taker_asset, maker_amount / taker_amount
    if taker_asset == "0" and maker_asset != "0":
        return maker_asset, taker_amount / maker_amount
    return None


def build_polymarket_trade_cases(
    markets: pd.DataFrame,
    trades: pd.DataFrame,
    blocks: pd.DataFrame,
) -> pd.DataFrame:
    """Create YES-probability cases from Polymarket CTF ``OrderFilled`` rows.

    Trade block numbers are joined to the upstream exact block timestamp mapping.
    A NO-token trade at price ``p`` becomes a YES probability of ``1 - p``.
    One observation is retained per question/timestamp; when ``log_index`` exists,
    the final log at that instant wins deterministically.
    """

    _require_columns(
        trades,
        (
            "block_number",
            "maker_asset_id",
            "taker_asset_id",
            "maker_amount",
            "taker_amount",
        ),
        label="Polymarket trades",
    )
    _require_columns(blocks, ("block_number", "timestamp"), label="Polymarket blocks")

    resolved = _polymarket_resolution_rows(markets)
    if resolved.empty or trades.empty or blocks.empty:
        return _empty_cases()

    token_rows: list[dict[str, object]] = []
    for _, row in resolved.iterrows():
        token_rows.extend(
            [
                {
                    "token_id": str(row["yes_token_id"]),
                    "token_side": "yes",
                    "question_id": row["question_id"],
                    "question_text": row["question_text"],
                    "resolved_at": row["resolved_at"],
                    "outcome": row["outcome"],
                },
                {
                    "token_id": str(row["no_token_id"]),
                    "token_side": "no",
                    "question_id": row["question_id"],
                    "question_text": row["question_text"],
                    "resolved_at": row["resolved_at"],
                    "outcome": row["outcome"],
                },
            ]
        )
    token_map = pd.DataFrame(token_rows)

    parsed_rows: list[dict[str, object]] = []
    for source_order, (_, row) in enumerate(trades.iterrows()):
        parsed = _trade_token_and_price(row)
        if parsed is None:
            continue
        token_id, token_price = parsed
        if not 0.0 <= token_price <= 1.0:
            continue
        parsed_rows.append(
            {
                "block_number": row["block_number"],
                "token_id": token_id,
                "token_price": token_price,
                "log_index": row.get("log_index", source_order),
                "_source_order": source_order,
            }
        )

    if not parsed_rows:
        return _empty_cases()

    parsed = pd.DataFrame(parsed_rows)
    block_times = blocks[["block_number", "timestamp"]].drop_duplicates(
        "block_number", keep="last"
    )
    joined = parsed.merge(
        block_times,
        on="block_number",
        how="inner",
        validate="many_to_one",
    ).merge(token_map, on="token_id", how="inner", validate="many_to_one")
    if joined.empty:
        return _empty_cases()

    market_probability = np.where(
        joined["token_side"].eq("yes"),
        joined["token_price"],
        1.0 - joined["token_price"],
    )

    cases = pd.DataFrame(
        {
            "question_id": joined["question_id"].astype(str),
            "question_text": joined["question_text"].astype(str),
            "forecasted_at": joined["timestamp"],
            "resolved_at": joined["resolved_at"],
            "market_price_timestamp": joined["timestamp"],
            "source_cutoff_at": joined["timestamp"],
            "market_probability": market_probability,
            "outcome": joined["outcome"].astype(int),
            "category": "unknown",
            "platform": "polymarket",
            "_log_index": pd.to_numeric(joined["log_index"], errors="coerce").fillna(-1),
            "_source_order": joined["_source_order"],
        }
    )

    cases["_sort_time"] = pd.to_datetime(cases["forecasted_at"], utc=True, errors="raise")
    cases.sort_values(
        ["question_id", "_sort_time", "_log_index", "_source_order"],
        inplace=True,
    )
    cases.drop_duplicates(
        subset=["question_id", "_sort_time"],
        keep="last",
        inplace=True,
    )
    cases.drop(
        columns=["_log_index", "_source_order", "_sort_time"],
        inplace=True,
    )
    return normalize_case_frame(cases)


def sample_latest_before_resolution(
    cases: pd.DataFrame,
    *,
    minimum_lead: str | pd.Timedelta = "7D",
) -> pd.DataFrame:
    """Select one latest market observation per question before a lead-time cutoff.

    This prevents highly traded questions from dominating a benchmark simply because
    they produced more trades. For example, a seven-day lead samples the last available
    price no later than seven days before the conservative resolution boundary.
    """

    normalized = normalize_case_frame(cases)
    lead = pd.Timedelta(minimum_lead)
    if lead < pd.Timedelta(0):
        raise ValueError("minimum_lead cannot be negative")

    eligible = normalized.loc[
        normalized["forecasted_at"] <= normalized["resolved_at"] - lead
    ].copy()
    if eligible.empty:
        return eligible

    eligible.sort_values(["question_id", "forecasted_at"], inplace=True)
    sampled = eligible.groupby("question_id", as_index=False, sort=True).tail(1).copy()
    sampled.sort_values(["forecasted_at", "question_id"], inplace=True)
    sampled.reset_index(drop=True, inplace=True)
    return normalize_case_frame(sampled)
