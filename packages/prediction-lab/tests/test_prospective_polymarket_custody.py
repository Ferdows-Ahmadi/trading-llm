from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from prediction_lab.prospective_polymarket_custody import (
    FrozenResponse,
    SELECTION_SEED,
    _rank,
    collect_prospective_custody,
    structural_check,
)


def market(
    market_id: str,
    event_id: str,
    *,
    end_date: str = "2026-09-30T00:00:00Z",
    description: str = "Resolves according to the named official source.",
) -> dict[str, object]:
    return {
        "id": market_id,
        "conditionId": f"condition-{market_id}",
        "question": f"Question {market_id}?",
        "slug": f"market-{market_id}",
        "description": description,
        "resolutionSource": "https://example.com/official",
        "endDate": end_date,
        "closed": False,
        "active": True,
        "enableOrderBook": True,
        "acceptingOrders": True,
        "outcomes": json.dumps(["Yes", "No"]),
        "clobTokenIds": json.dumps([f"yes-{market_id}", f"no-{market_id}"]),
        "volumeNum": 10000,
        "liquidityNum": 5000,
        "category": "test",
        "events": [
            {
                "id": event_id,
                "slug": f"event-{event_id}",
                "resolutionSource": "https://example.com/event-official",
            }
        ],
    }


class FakeClient:
    def __init__(
        self,
        markets: list[dict[str, object]],
        *,
        bad_token: str | None = None,
    ) -> None:
        self.markets = markets
        self.bad_token = bad_token
        self.queried_tokens: list[str] = []

    @staticmethod
    def response(payload: object, url: str, params: dict[str, object]) -> FrozenResponse:
        raw = json.dumps(payload, sort_keys=True).encode()
        return FrozenResponse(
            payload=payload,
            raw=raw,
            acquired_at="2026-09-13T12:00:05+00:00",
            url=url,
            params=params,
        )

    def gamma_markets_page(self, params: dict[str, object]) -> FrozenResponse:
        offset = int(params["offset"])
        limit = int(params["limit"])
        payload = self.markets[offset : offset + limit]
        return self.response(payload, "https://gamma.test/markets", params)

    def clob_price(self, token_id: str, side: str) -> FrozenResponse:
        self.queried_tokens.append(token_id)
        if token_id == self.bad_token:
            value = "0.99" if side == "BUY" else "0.01"
        else:
            value = "0.45" if side == "BUY" else "0.55"
        return self.response(
            {"price": value},
            "https://clob.test/price",
            {"token_id": token_id, "side": side},
        )

    def clob_midpoint(self, token_id: str) -> FrozenResponse:
        self.queried_tokens.append(token_id)
        value = "0.50"
        return self.response(
            {"mid_price": value},
            "https://clob.test/midpoint",
            {"token_id": token_id},
        )


def test_structural_check_enforces_contract_custody() -> None:
    earliest = pd.Timestamp("2026-09-20T00:00:00Z")
    latest = pd.Timestamp("2026-10-28T00:00:00Z")
    valid, reasons = structural_check(
        market("10", "event-a"),
        earliest_end=earliest,
        latest_end=latest,
    )
    assert reasons == []
    assert valid is not None
    missing, reasons = structural_check(
        market("11", "event-b", description=""),
        earliest_end=earliest,
        latest_end=latest,
    )
    assert missing is None
    assert "missing_contract_description" in reasons


def test_event_representative_is_hash_deterministic_and_has_no_fallback(
    tmp_path: Path,
) -> None:
    first = market("20", "same-event")
    second = market("21", "same-event")
    chosen = min(
        [first, second],
        key=lambda item: _rank(SELECTION_SEED, "same-event", item["id"]),
    )
    rejected = second if chosen is first else first
    fake = FakeClient(
        [first, second, market("30", "other-event")],
        bad_token=f"yes-{chosen['id']}",
    )
    output = tmp_path / "custody"
    summary = collect_prospective_custody(
        fake,  # type: ignore[arg-type]
        output_directory=output,
        code_commit="test-commit",
        snapshot_reference_at="2026-09-13T00:00:00Z",
    )
    cohort = [
        json.loads(line)
        for line in (output / "cohort.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert summary["event_representatives"] == 2
    assert {row["event_id"] for row in cohort} == {"other-event"}
    assert f"yes-{rejected['id']}" not in fake.queried_tokens


def test_custody_freezes_raw_and_keeps_events_independent(tmp_path: Path) -> None:
    fake = FakeClient(
        [
            market("40", "event-40"),
            market("41", "event-41"),
            market("42", "event-42"),
        ]
    )
    output = tmp_path / "custody"
    summary = collect_prospective_custody(
        fake,  # type: ignore[arg-type]
        output_directory=output,
        code_commit="test-commit",
        snapshot_reference_at="2026-09-13T00:00:00Z",
    )
    rows = [
        json.loads(line)
        for line in (output / "cohort.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert summary["selected_rows"] == 3
    assert summary["selected_event_groups"] == 3
    assert len({row["event_id"] for row in rows}) == 3
    assert all(row["market_probability"] == 0.5 for row in rows)
    assert all(row["contract_sha256"] for row in rows)
    assert (output / "raw" / "gamma" / "page-000.json").is_file()
    assert summary["forecaster_run"] is False
    assert summary["reserved_holdout_accessed"] is False
