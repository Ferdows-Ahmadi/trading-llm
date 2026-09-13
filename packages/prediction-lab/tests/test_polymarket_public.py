from __future__ import annotations

import httpx
import pandas as pd
import pytest

from prediction_lab.polymarket_public import (
    PolymarketPublicAPIError,
    PolymarketPublicClient,
    collect_public_polymarket_cases,
)

GAMMA_URL = "https://gamma.test"
DATA_URL = "https://data.test"


def _response(payload: object) -> httpx.Response:
    return httpx.Response(200, json=payload)


def _market(index: int) -> dict[str, object]:
    opened = pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(days=index * 20)
    closed = opened + pd.Timedelta(days=20)
    yes_wins = index % 2 == 1
    return {
        "id": str(1000 + index),
        "conditionId": f"condition-{index}",
        "question": f"Will event {index} happen?",
        "startDate": opened.isoformat(),
        "endDate": (opened + pd.Timedelta(days=365)).isoformat(),
        "closedTime": closed.isoformat(),
        "closed": True,
        "volumeNum": 1000.0,
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["1", "0"]' if yes_wins else '["0", "1"]',
        "events": [{"id": f"event-{index // 2}"}],
    }


def test_collect_polymarket_cases_uses_actual_close_and_converts_no_price() -> None:
    markets = [_market(index) for index in range(4)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gamma.test":
            assert request.url.path == "/markets/keyset"
            return _response({"markets": markets, "next_cursor": ""})
        if request.url.host == "data.test":
            condition_id = request.url.params["market"]
            index = int(condition_id.rsplit("-", maxsplit=1)[1])
            closed = pd.Timestamp(markets[index]["closedTime"])
            created = closed - pd.Timedelta(days=8)
            return _response(
                [
                    {
                        "conditionId": condition_id,
                        "asset": f"asset-{index}",
                        "price": 0.7,
                        "timestamp": int(created.timestamp()),
                        "outcome": "No" if index == 0 else "Yes",
                        "outcomeIndex": 1 if index == 0 else 0,
                        "side": "BUY",
                    }
                ]
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PolymarketPublicClient(
        gamma_url=GAMMA_URL,
        data_url=DATA_URL,
        client=http_client,
    )
    cases, acquisition, used_markets, used_trades = collect_public_polymarket_cases(
        client,
        max_questions=4,
        candidate_multiplier=1,
        minimum_lead="7D",
        maximum_price_staleness="3D",
        minimum_volume=100.0,
        max_market_pages=1,
    )

    first = cases.loc[cases["question_id"] == "1000"].iloc[0]
    assert len(cases) == 4
    assert first["market_probability"] == pytest.approx(0.3)
    assert first["resolved_at"] == pd.Timestamp(markets[0]["closedTime"])
    assert first["forecasted_at"] <= first["resolved_at"] - pd.Timedelta(days=7)
    assert first["event_id"] == "polymarket-event:event-0"
    assert first["snapshot_staleness_hours"] == pytest.approx(24.0)
    assert acquisition.maximum_price_staleness == "3 days 00:00:00"
    assert acquisition.usable_cases == 4
    assert len(used_markets) == len(used_trades) == 4
    http_client.close()


def test_short_actual_lifetime_is_rejected_even_when_scheduled_end_is_far_away() -> None:
    short = _market(0)
    opened = pd.Timestamp(short["startDate"])
    short["closedTime"] = (opened + pd.Timedelta(days=2)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gamma.test":
            return _response({"markets": [short], "next_cursor": ""})
        raise AssertionError("Trade endpoint must not be called for a short-lived market")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PolymarketPublicClient(
        gamma_url=GAMMA_URL,
        data_url=DATA_URL,
        client=http_client,
    )
    candidates = client.fetch_candidate_markets(
        minimum_volume=100.0,
        minimum_lifetime=pd.Timedelta(days=7),
        target_items=10,
        max_pages=1,
    )

    assert candidates == []
    http_client.close()


def test_trade_search_widens_window_until_history_exists() -> None:
    requests: list[tuple[int, int]] = []
    target = pd.Timestamp("2026-06-01T00:00:00Z")

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["start"])
        end = int(request.url.params["end"])
        requests.append((start, end))
        if len(requests) < 3:
            return _response([])
        created = target - pd.Timedelta(days=20)
        return _response(
            [
                {
                    "conditionId": "condition-x",
                    "price": 0.4,
                    "timestamp": int(created.timestamp()),
                    "outcome": "Yes",
                }
            ]
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PolymarketPublicClient(
        gamma_url=GAMMA_URL,
        data_url=DATA_URL,
        client=http_client,
    )
    trade = client.latest_trade_before(condition_id="condition-x", target=target)

    assert trade is not None
    assert len(requests) == 3
    assert trade["price"] == pytest.approx(0.4)
    http_client.close()


def test_collect_rejects_prices_staler_than_configured_window() -> None:
    markets = [_market(index) for index in range(4)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "gamma.test":
            return _response({"markets": markets, "next_cursor": ""})
        condition_id = request.url.params["market"]
        index = int(condition_id.rsplit("-", maxsplit=1)[1])
        closed = pd.Timestamp(markets[index]["closedTime"])
        created = closed - pd.Timedelta(days=12)
        return _response(
            [
                {
                    "conditionId": condition_id,
                    "price": 0.5,
                    "timestamp": int(created.timestamp()),
                    "outcome": "Yes",
                }
            ]
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = PolymarketPublicClient(
        gamma_url=GAMMA_URL,
        data_url=DATA_URL,
        client=http_client,
    )
    with pytest.raises(PolymarketPublicAPIError, match="Only 0 usable cases"):
        collect_public_polymarket_cases(
            client,
            max_questions=4,
            candidate_multiplier=1,
            minimum_lead="7D",
            maximum_price_staleness="3D",
            max_market_pages=1,
        )
    http_client.close()
