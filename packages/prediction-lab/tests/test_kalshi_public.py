from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pandas as pd
import pytest

from prediction_lab.kalshi_public import (
    KalshiPublicClient,
    collect_public_kalshi_cases,
)

BASE_URL = "https://kalshi.test/trade-api/v2"


def _json_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json=payload)


def test_latest_trade_uses_historical_tier_before_cutoff() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        assert parse_qs(request.url.query.decode())["ticker"] == ["ABC"]
        if request.url.path.endswith("/historical/trades"):
            return _json_response(
                {
                    "trades": [
                        {
                            "trade_id": "t1",
                            "ticker": "ABC",
                            "yes_price_dollars": "0.4200",
                            "created_time": "2026-01-09T12:00:00Z",
                        }
                    ],
                    "cursor": "",
                }
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = KalshiPublicClient(base_url=BASE_URL, client=http_client)
    trade = client.latest_trade_before(
        ticker="ABC",
        target=pd.Timestamp("2026-01-10T00:00:00Z"),
        trades_cutoff=pd.Timestamp("2026-01-15T00:00:00Z"),
    )

    assert trade is not None
    assert trade["trade_id"] == "t1"
    assert paths == ["/trade-api/v2/historical/trades"]
    http_client.close()


def test_latest_trade_falls_back_to_archive_when_live_is_empty() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/markets/trades"):
            return _json_response({"trades": [], "cursor": ""})
        if request.url.path.endswith("/historical/trades"):
            return _json_response(
                {
                    "trades": [
                        {
                            "trade_id": "old",
                            "ticker": "ABC",
                            "yes_price_dollars": "0.3300",
                            "created_time": "2026-01-14T23:00:00Z",
                        }
                    ],
                    "cursor": "",
                }
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = KalshiPublicClient(base_url=BASE_URL, client=http_client)
    trade = client.latest_trade_before(
        ticker="ABC",
        target=pd.Timestamp("2026-02-01T00:00:00Z"),
        trades_cutoff=pd.Timestamp("2026-01-15T00:00:00Z"),
    )

    assert trade is not None
    assert trade["trade_id"] == "old"
    assert paths == [
        "/trade-api/v2/markets/trades",
        "/trade-api/v2/historical/trades",
    ]
    http_client.close()


def test_collect_public_cases_builds_normalized_fixed_lead_rows() -> None:
    markets = []
    for index in range(4):
        close = pd.Timestamp("2026-03-20T00:00:00Z") + pd.Timedelta(days=index * 10)
        markets.append(
            {
                "ticker": f"MKT-{index}",
                "title": f"Will event {index} happen?",
                "market_type": "binary",
                "result": "yes" if index % 2 else "no",
                "open_time": (close - pd.Timedelta(days=30)).isoformat(),
                "close_time": close.isoformat(),
                "settlement_ts": (close + pd.Timedelta(hours=2)).isoformat(),
                "volume_fp": "500.00",
                "is_provisional": False,
            }
        )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/historical/cutoff"):
            return _json_response(
                {
                    "market_settled_ts": "2025-12-01T00:00:00Z",
                    "trades_created_ts": "2025-12-01T00:00:00Z",
                }
            )
        if path.endswith("/historical/markets"):
            return _json_response({"markets": markets, "cursor": ""})
        if path.endswith("/markets"):
            return _json_response({"markets": markets, "cursor": ""})
        if path.endswith("/markets/trades"):
            ticker = request.url.params["ticker"]
            market = next(item for item in markets if item["ticker"] == ticker)
            close = pd.Timestamp(market["close_time"])
            created = close - pd.Timedelta(days=8)
            return _json_response(
                {
                    "trades": [
                        {
                            "trade_id": f"trade-{ticker}",
                            "ticker": ticker,
                            "yes_price_dollars": "0.6000",
                            "created_time": created.isoformat(),
                        }
                    ],
                    "cursor": "",
                }
            )
        raise AssertionError(f"Unexpected path: {path}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = KalshiPublicClient(base_url=BASE_URL, client=http_client)
    cases, acquisition, used_markets, used_trades = collect_public_kalshi_cases(
        client,
        max_questions=4,
        candidate_multiplier=1,
        minimum_lead="7D",
        minimum_volume=100,
        max_market_pages=1,
        max_trade_pages=1,
    )

    assert len(cases) == 4
    assert cases["question_id"].nunique() == 4
    assert cases["market_probability"].tolist() == pytest.approx([0.6] * 4)
    assert all(cases["forecasted_at"] <= cases["resolved_at"] - pd.Timedelta(days=7))
    assert acquisition.usable_cases == 4
    assert len(used_markets) == len(used_trades) == 4
    http_client.close()
