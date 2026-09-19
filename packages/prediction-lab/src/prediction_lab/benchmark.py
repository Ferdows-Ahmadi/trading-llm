from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from prediction_lab.cases import normalize_case_frame

PINNED_JON_BECKER_REVISION = "2276382cb616107db8c8647803bffa4a0d7091f8"


class BenchmarkBuildError(RuntimeError):
    """Raised when a reproducible benchmark cannot be built from upstream data."""


def _parquet_glob(directory: Path, *, label: str) -> str:
    files = sorted(directory.glob("*.parquet"))
    if not files:
        raise BenchmarkBuildError(f"No Parquet files found for {label}: {directory}")
    return (directory / "*.parquet").as_posix()


def _even_temporal_sample(cases: pd.DataFrame, max_questions: int | None) -> pd.DataFrame:
    if max_questions is None or len(cases) <= max_questions:
        return cases.reset_index(drop=True)
    if max_questions < 2:
        raise ValueError("max_questions must be at least 2 when provided")

    ordered = cases.sort_values(["forecasted_at", "question_id"]).reset_index(drop=True)
    positions = np.linspace(0, len(ordered) - 1, num=max_questions, dtype=int)
    return ordered.iloc[positions].reset_index(drop=True)


def build_kalshi_cases_from_parquet(
    source_root: str | Path,
    *,
    minimum_lead: str | pd.Timedelta = "7D",
    min_volume: int = 100,
    max_questions: int | None = 1000,
) -> pd.DataFrame:
    """Build one fixed-lead Kalshi case per resolved market from Becker Parquet data.

    The query runs in DuckDB so the full trade archive is not loaded into Python.
    For each finalized market, it selects the latest historical trade no later than
    ``minimum_lead`` before the market close. If close time is unavailable, the
    upstream fetch timestamp is used as a conservative fallback.
    """

    if min_volume < 0:
        raise ValueError("min_volume cannot be negative")

    lead = pd.Timedelta(minimum_lead)
    if lead < pd.Timedelta(0):
        raise ValueError("minimum_lead cannot be negative")
    lead_seconds = int(lead.total_seconds())

    root = Path(source_root)
    markets_glob = _parquet_glob(root / "kalshi" / "markets", label="Kalshi markets")
    trades_glob = _parquet_glob(root / "kalshi" / "trades", label="Kalshi trades")

    query = """
        WITH market_snapshots AS (
            SELECT
                ticker,
                title,
                event_ticker,
                status,
                result,
                volume,
                close_time,
                _fetched_at,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY _fetched_at DESC
                ) AS snapshot_rank
            FROM read_parquet(?, union_by_name = true)
        ),
        resolved AS (
            SELECT
                ticker,
                title,
                event_ticker,
                result,
                COALESCE(close_time, _fetched_at) AS resolved_at
            FROM market_snapshots
            WHERE snapshot_rank = 1
              AND LOWER(status) = 'finalized'
              AND LOWER(result) IN ('yes', 'no')
              AND volume >= ?
              AND COALESCE(close_time, _fetched_at) IS NOT NULL
        ),
        eligible AS (
            SELECT
                r.ticker AS question_id,
                r.title AS question_text,
                t.created_time AS forecasted_at,
                r.resolved_at,
                t.created_time AS market_price_timestamp,
                t.created_time AS source_cutoff_at,
                CAST(t.yes_price AS DOUBLE) / 100.0 AS market_probability,
                CASE WHEN LOWER(r.result) = 'yes' THEN 1 ELSE 0 END AS outcome,
                'unknown' AS category,
                'kalshi' AS platform,
                t.trade_id,
                ROW_NUMBER() OVER (
                    PARTITION BY r.ticker
                    ORDER BY t.created_time DESC, t.trade_id DESC
                ) AS trade_rank
            FROM read_parquet(?, union_by_name = true) AS t
            INNER JOIN resolved AS r ON r.ticker = t.ticker
            WHERE t.yes_price BETWEEN 1 AND 99
              AND t.created_time <= r.resolved_at - (? * INTERVAL '1 second')
        )
        SELECT
            question_id,
            question_text,
            forecasted_at,
            resolved_at,
            market_price_timestamp,
            source_cutoff_at,
            market_probability,
            outcome,
            category,
            platform
        FROM eligible
        WHERE trade_rank = 1
        ORDER BY forecasted_at, question_id
    """

    connection = duckdb.connect()
    try:
        cases = connection.execute(
            query,
            [markets_glob, int(min_volume), trades_glob, lead_seconds],
        ).df()
    except duckdb.Error as exc:
        raise BenchmarkBuildError(f"DuckDB failed while building Kalshi cases: {exc}") from exc
    finally:
        connection.close()

    if cases.empty:
        raise BenchmarkBuildError(
            "No eligible Kalshi benchmark cases were found; check lead time and source data"
        )

    normalized = normalize_case_frame(cases)
    return _even_temporal_sample(normalized, max_questions)


def choose_temporal_holdout_start(
    cases: pd.DataFrame,
    *,
    holdout_fraction: float = 0.25,
) -> pd.Timestamp:
    """Choose a deterministic time cutoff that reserves the newest questions as holdout."""

    if not 0.05 <= holdout_fraction <= 0.5:
        raise ValueError("holdout_fraction must be between 0.05 and 0.5")

    normalized = normalize_case_frame(cases)
    if len(normalized) < 4:
        raise BenchmarkBuildError("At least four cases are required for a temporal split")

    ordered = normalized.sort_values(["forecasted_at", "question_id"]).reset_index(drop=True)
    holdout_size = max(1, int(np.ceil(len(ordered) * holdout_fraction)))
    cutoff_index = len(ordered) - holdout_size
    if cutoff_index <= 0:
        raise BenchmarkBuildError("Holdout split would leave no development cases")
    return pd.Timestamp(ordered.loc[cutoff_index, "forecasted_at"])
