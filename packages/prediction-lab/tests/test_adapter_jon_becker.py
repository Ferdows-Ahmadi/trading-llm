from __future__ import annotations

import json

import pandas as pd
import pytest

from prediction_lab.adapters.jon_becker import (
    build_kalshi_trade_cases,
    build_polymarket_trade_cases,
    sample_latest_before_resolution,
)


def test_kalshi_yes_price_becomes_probability() -> None:
    markets = pd.DataFrame(
        [
            {
                "ticker": "MKT-A",
                "title": "Will A happen?",
                "status": "finalized",
                "result": "yes",
                "_fetched_at": "2026-01-20T00:00:00Z",
            }
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "ticker": "MKT-A",
                "yes_price": 65,
                "created_time": "2026-01-10T00:00:00Z",
            }
        ]
    )

    cases = build_kalshi_trade_cases(markets, trades)
    assert len(cases) == 1
    assert cases.loc[0, "market_probability"] == pytest.approx(0.65)
    assert cases.loc[0, "outcome"] == 1
    assert cases.loc[0, "platform"] == "kalshi"


def test_polymarket_no_token_price_is_converted_to_yes_probability() -> None:
    markets = pd.DataFrame(
        [
            {
                "id": "market-a",
                "question": "Will A happen?",
                "closed": True,
                "outcomes": json.dumps(["Yes", "No"]),
                "outcome_prices": json.dumps([1.0, 0.0]),
                "clob_token_ids": json.dumps(["yes-a", "no-a"]),
                "_fetched_at": "2026-01-20T00:00:00Z",
            }
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "block_number": 123,
                "log_index": 4,
                "maker_asset_id": "0",
                "taker_asset_id": "no-a",
                "maker_amount": 300_000,
                "taker_amount": 1_000_000,
            }
        ]
    )
    blocks = pd.DataFrame(
        [{"block_number": 123, "timestamp": "2026-01-10T00:00:00Z"}]
    )

    cases = build_polymarket_trade_cases(markets, trades, blocks)
    assert len(cases) == 1
    assert cases.loc[0, "market_probability"] == pytest.approx(0.70)
    assert cases.loc[0, "outcome"] == 1
    assert cases.loc[0, "platform"] == "polymarket"


def test_latest_before_resolution_respects_lead_time() -> None:
    cases = pd.DataFrame(
        [
            {
                "question_id": "q1",
                "question_text": "Question?",
                "forecasted_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-01-20T00:00:00Z",
                "market_price_timestamp": "2026-01-01T00:00:00Z",
                "source_cutoff_at": "2026-01-01T00:00:00Z",
                "market_probability": 0.40,
                "outcome": 1,
            },
            {
                "question_id": "q1",
                "question_text": "Question?",
                "forecasted_at": "2026-01-10T00:00:00Z",
                "resolved_at": "2026-01-20T00:00:00Z",
                "market_price_timestamp": "2026-01-10T00:00:00Z",
                "source_cutoff_at": "2026-01-10T00:00:00Z",
                "market_probability": 0.55,
                "outcome": 1,
            },
            {
                "question_id": "q1",
                "question_text": "Question?",
                "forecasted_at": "2026-01-18T00:00:00Z",
                "resolved_at": "2026-01-20T00:00:00Z",
                "market_price_timestamp": "2026-01-18T00:00:00Z",
                "source_cutoff_at": "2026-01-18T00:00:00Z",
                "market_probability": 0.80,
                "outcome": 1,
            },
        ]
    )

    sampled = sample_latest_before_resolution(cases, minimum_lead="7D")
    assert len(sampled) == 1
    assert sampled.loc[0, "market_probability"] == pytest.approx(0.55)
    assert sampled.loc[0, "forecasted_at"] == pd.Timestamp("2026-01-10T00:00:00Z")
