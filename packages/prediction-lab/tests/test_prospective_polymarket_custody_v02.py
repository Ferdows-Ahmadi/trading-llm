from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab import prospective_polymarket_custody_v02 as v02


def frozen(payload: object) -> base.FrozenResponse:
    raw = json.dumps(payload, sort_keys=True).encode()
    return base.FrozenResponse(
        payload=payload,
        raw=raw,
        acquired_at="2026-09-13T19:00:00+00:00",
        url="https://clob.polymarket.com/midpoint",
        params={"token_id": "test"},
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"mid": "0.45"}, 0.45),
        ({"mid_price": "0.45"}, 0.45),
        ({"mid": "0.45", "mid_price": "0.450"}, 0.45),
    ],
)
def test_midpoint_aliases_accept_frozen_equivalent_shapes(
    payload: dict[str, str],
    expected: float,
) -> None:
    value, reasons = v02._midpoint_value(frozen(payload))
    assert value == expected
    assert reasons == []


def test_midpoint_aliases_reject_conflict() -> None:
    value, reasons = v02._midpoint_value(
        frozen({"mid": "0.45", "mid_price": "0.46"})
    )
    assert value is None
    assert reasons == ["conflicting_midpoint_aliases"]


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({}, "missing_midpoint_field"),
        ({"other": "0.45"}, "missing_midpoint_field"),
        ({"mid": "not-a-number"}, "invalid_clob_price"),
        ({"mid": "NaN"}, "invalid_clob_price"),
        ({"mid": "Infinity"}, "invalid_clob_price"),
        ({"mid": "bad", "mid_price": "0.45"}, "invalid_clob_price"),
    ],
)
def test_midpoint_aliases_reject_missing_or_nonnumeric(
    payload: dict[str, str],
    reason: str,
) -> None:
    value, reasons = v02._midpoint_value(frozen(payload))
    assert value is None
    assert reasons == [reason]


class FakeKeysetClient:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    def gamma_markets_keyset_page(
        self,
        params: dict[str, object],
    ) -> base.FrozenResponse:
        self.calls.append(dict(params))
        if not self.payloads:
            raise AssertionError("Unexpected extra keyset request")
        payload = self.payloads.pop(0)
        raw = json.dumps(payload, sort_keys=True).encode()
        return base.FrozenResponse(
            payload=payload,
            raw=raw,
            acquired_at="2026-09-13T19:00:00+00:00",
            url="https://gamma-api.polymarket.com/markets/keyset",
            params=dict(params),
        )


def test_v02_keyset_query_uses_frozen_90_day_window_and_opaque_cursor(
    tmp_path: Path,
) -> None:
    fake = FakeKeysetClient(
        [
            {"markets": [{"id": "10"}], "next_cursor": "opaque+/=cursor"},
            {"markets": [{"id": "11"}], "next_cursor": None},
        ]
    )
    reference = pd.Timestamp("2026-09-13T19:00:00Z")

    universe, receipts = v02._collect_keyset_universe(
        fake,  # type: ignore[arg-type]
        raw_gamma=tmp_path / "raw" / "gamma",
        earliest_end=reference + v02.MIN_HORIZON,
        latest_end=reference + v02.MAX_HORIZON,
    )

    assert [row["id"] for row in universe] == ["10", "11"]
    assert fake.calls[0]["end_date_min"] == "2026-09-20T19:00:00Z"
    assert fake.calls[0]["end_date_max"] == "2026-12-12T19:00:00Z"
    assert fake.calls[0]["limit"] == 100
    assert "after_cursor" not in fake.calls[0]
    assert fake.calls[1]["after_cursor"] == "opaque+/=cursor"
    assert all("offset" not in call for call in fake.calls)
    assert len(receipts) == 2


def test_v02_frozen_identity_and_limits() -> None:
    assert v02.PROTOCOL_COMMIT == "12a39fcc156ace92356e3d6b05b7a444f6c23679"
    assert v02.SELECTION_SEED == (
        "prospective-development-custody-v0.2-selection-seed-2026-09-13"
    )
    assert v02.MIN_HORIZON == pd.Timedelta("7D")
    assert v02.MAX_HORIZON == pd.Timedelta("90D")
    assert v02.MAX_PAGES == 1000
    assert v02.TARGET_COHORT == 100
    assert v02.ADEQUACY_FLOOR == 60
