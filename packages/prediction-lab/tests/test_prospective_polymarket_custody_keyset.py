from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from prediction_lab import prospective_polymarket_custody as base
from prediction_lab.prospective_polymarket_custody_keyset import (
    _collect_keyset_universe,
)


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
            acquired_at="2026-09-13T12:00:05+00:00",
            url="https://gamma.test/markets/keyset",
            params=dict(params),
        )


def collect(fake: FakeKeysetClient, tmp_path: Path):
    return _collect_keyset_universe(
        fake,  # type: ignore[arg-type]
        raw_gamma=tmp_path / "raw" / "gamma",
        earliest_end=pd.Timestamp("2026-09-20T00:00:00Z"),
        latest_end=pd.Timestamp("2026-10-28T00:00:00Z"),
    )


def test_keyset_pagination_replays_exact_opaque_cursor_and_freezes_pages(
    tmp_path: Path,
) -> None:
    cursor = "opaque+/=cursor-value"
    fake = FakeKeysetClient(
        [
            {"markets": [{"id": "10"}], "next_cursor": cursor},
            {"markets": [{"id": "11"}], "next_cursor": ""},
        ]
    )

    universe, receipts = collect(fake, tmp_path)

    assert [row["id"] for row in universe] == ["10", "11"]
    assert "after_cursor" not in fake.calls[0]
    assert fake.calls[1]["after_cursor"] == cursor
    assert all("offset" not in call for call in fake.calls)
    assert len(receipts) == 2
    assert receipts[0]["next_cursor_present"] is True
    assert receipts[0]["next_cursor_sha256"] == base._sha256(cursor.encode())
    assert receipts[1]["next_cursor_present"] is False
    assert (tmp_path / "raw" / "gamma" / "page-000.json").is_file()
    assert (tmp_path / "raw" / "gamma" / "page-001.json").is_file()


def test_keyset_rejects_malformed_cursor_type(tmp_path: Path) -> None:
    fake = FakeKeysetClient(
        [{"markets": [{"id": "10"}], "next_cursor": 123}]
    )

    with pytest.raises(base.ProspectiveCustodyError, match="next_cursor must be a string"):
        collect(fake, tmp_path)


def test_keyset_rejects_repeated_cursor(tmp_path: Path) -> None:
    fake = FakeKeysetClient(
        [
            {"markets": [{"id": "10"}], "next_cursor": "same"},
            {"markets": [{"id": "11"}], "next_cursor": "same"},
        ]
    )

    with pytest.raises(base.ProspectiveCustodyError, match="cursor repeated"):
        collect(fake, tmp_path)


def test_keyset_rejects_duplicate_market_id_across_pages(tmp_path: Path) -> None:
    fake = FakeKeysetClient(
        [
            {"markets": [{"id": "10"}], "next_cursor": "next"},
            {"markets": [{"id": "10"}], "next_cursor": None},
        ]
    )

    with pytest.raises(base.ProspectiveCustodyError, match="Duplicate market ID"):
        collect(fake, tmp_path)
