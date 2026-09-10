from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from prediction_lab.benchmark import (
    build_kalshi_cases_from_parquet,
    choose_temporal_holdout_start,
)


def _write_parquet_fixture(path: Path, table_name: str, sql: str) -> None:
    connection = duckdb.connect()
    try:
        connection.execute(f"CREATE TABLE {table_name} AS {sql}")
        escaped = path.as_posix().replace("'", "''")
        connection.execute(f"COPY {table_name} TO '{escaped}' (FORMAT PARQUET)")
    finally:
        connection.close()


def test_build_kalshi_cases_selects_latest_eligible_trade(tmp_path: Path) -> None:
    markets_dir = tmp_path / "kalshi" / "markets"
    trades_dir = tmp_path / "kalshi" / "trades"
    markets_dir.mkdir(parents=True)
    trades_dir.mkdir(parents=True)

    _write_parquet_fixture(
        markets_dir / "markets.parquet",
        "markets",
        """
        SELECT * FROM (VALUES
            ('Q1', 'Will Q1 happen?', 'TEST', 'finalized', 'yes', 500,
             TIMESTAMPTZ '2026-01-20 00:00:00+00', TIMESTAMPTZ '2026-01-21 00:00:00+00'),
            ('Q2', 'Will Q2 happen?', 'TEST', 'finalized', 'no', 500,
             TIMESTAMPTZ '2026-02-20 00:00:00+00', TIMESTAMPTZ '2026-02-21 00:00:00+00')
        ) AS t(ticker, title, event_ticker, status, result, volume, close_time, _fetched_at)
        """,
    )
    _write_parquet_fixture(
        trades_dir / "trades.parquet",
        "trades",
        """
        SELECT * FROM (VALUES
            ('t1', 'Q1', 40, TIMESTAMPTZ '2026-01-01 00:00:00+00'),
            ('t2', 'Q1', 55, TIMESTAMPTZ '2026-01-10 00:00:00+00'),
            ('t3', 'Q1', 90, TIMESTAMPTZ '2026-01-18 00:00:00+00'),
            ('t4', 'Q2', 35, TIMESTAMPTZ '2026-02-10 00:00:00+00')
        ) AS t(trade_id, ticker, yes_price, created_time)
        """,
    )

    cases = build_kalshi_cases_from_parquet(
        tmp_path,
        minimum_lead="7D",
        max_questions=None,
    )
    q1 = cases.loc[cases["question_id"] == "Q1"].iloc[0]

    assert len(cases) == 2
    assert q1["market_probability"] == pytest.approx(0.55)
    assert q1["forecasted_at"] == pd.Timestamp("2026-01-10T00:00:00Z")
    assert q1["resolved_at"] == pd.Timestamp("2026-01-20T00:00:00Z")


def test_choose_temporal_holdout_start_reserves_newest_fraction() -> None:
    rows = []
    for index in range(8):
        timestamp = pd.Timestamp("2025-01-01T00:00:00Z") + pd.Timedelta(days=index)
        rows.append(
            {
                "question_id": f"q{index}",
                "question_text": f"Question {index}?",
                "forecasted_at": timestamp,
                "resolved_at": timestamp + pd.Timedelta(days=30),
                "market_price_timestamp": timestamp,
                "source_cutoff_at": timestamp,
                "market_probability": 0.5,
                "outcome": index % 2,
            }
        )

    cutoff = choose_temporal_holdout_start(pd.DataFrame(rows), holdout_fraction=0.25)
    assert cutoff == pd.Timestamp("2025-01-07T00:00:00Z")
