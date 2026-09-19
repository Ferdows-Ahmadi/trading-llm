from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from prediction_lab.historical_validity_sources_v2 import (
    HistoricalSourceV2Error,
    V2Capture,
    _freeze_content,
    derive_v2_urls,
    discover_v2_sources,
    load_v1_locators,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _locator(*, slug: str = "market-slug", event_slug: str | None = None) -> dict[str, object]:
    events: list[dict[str, object]] = []
    if event_slug is not None:
        events.append({"id": "e1", "slug": event_slug, "title": "Event"})
    return {
        "market": {"id": "123", "slug": slug, "question": "Will it happen?"},
        "events": events,
    }


def test_derive_v2_urls_uses_all_frozen_slug_patterns() -> None:
    urls = derive_v2_urls(_locator(event_slug="event-slug"))
    assert urls == [
        ("market-page:market-slug", "https://polymarket.com/market/market-slug"),
        ("event-page:market-slug", "https://polymarket.com/event/market-slug"),
        (
            "gamma-market-slug",
            "https://gamma-api.polymarket.com/markets/slug/market-slug",
        ),
        ("event-page:event-slug:event-slug", "https://polymarket.com/event/event-slug"),
        (
            "gamma-event-slug:event-slug",
            "https://gamma-api.polymarket.com/events/slug/event-slug",
        ),
    ]


def test_derive_v2_urls_rejects_unsafe_slug() -> None:
    with pytest.raises(HistoricalSourceV2Error, match="Unsafe frozen locator slug"):
        derive_v2_urls(_locator(slug="../../oops"))


def test_load_v1_locators_rejects_price_metadata(tmp_path: Path) -> None:
    path = tmp_path / "locators.jsonl"
    _write_jsonl(
        path,
        [
            {
                "question_id": "123",
                "locator_status": "success",
                "locator": {
                    "market": {"id": "123", "slug": "safe", "outcomePrices": "[1,0]"},
                    "events": [],
                },
            }
        ],
    )
    with pytest.raises(HistoricalSourceV2Error, match="forbidden price/outcome"):
        load_v1_locators(path, expected_rows=1)


def test_freeze_json_finds_nested_market_and_matches_question(tmp_path: Path) -> None:
    payload = {
        "id": "event-1",
        "markets": [
            {
                "id": "123",
                "question": "Will it happen?",
                "description": "Rules",
                "resolutionSource": "https://example.com/result",
            }
        ],
    }
    result = _freeze_content(
        body=json.dumps(payload).encode(),
        mime="application/json",
        market_id="123",
        benchmark_question="Will it happen?",
        provider="test",
        raw_directory=tmp_path / "raw",
        text_directory=tmp_path / "text",
    )
    assert result["historical_market_object_found"] is True
    assert result["benchmark_question_exact_match"] is True
    assert result["historical_resolution_source"] == "https://example.com/result"


def test_freeze_html_records_visible_text_match(tmp_path: Path) -> None:
    result = _freeze_content(
        body=b"<html><body><h1>Will it happen?</h1><script>ignore me</script></body></html>",
        mime="text/html",
        market_id="123",
        benchmark_question="Will it happen?",
        provider="test",
        raw_directory=tmp_path / "raw",
        text_directory=tmp_path / "text",
    )
    assert result["benchmark_question_exact_match"] is True
    assert result["text_chars"] > 0


class _FakeProvider:
    provider_name = "fake"

    def __init__(self, *, capture: bool) -> None:
        self.capture = capture

    def latest_capture_before(self, url: str, *, cutoff: object) -> V2Capture | None:
        del cutoff
        if not self.capture:
            return None
        return V2Capture(
            provider=self.provider_name,
            timestamp=pd.Timestamp("2025-01-01T00:00:00Z"),
            requested_url=url,
            captured_url=url,
            mime="text/html",
            status="200",
            identity="digest",
            replay_reference="fake://capture",
            provider_record={"url": url},
        )

    def freeze_body(self, capture: V2Capture) -> bytes:
        del capture
        return b"<html><body>Will it happen?</body></html>"


def _single_candidate_fixture(tmp_path: Path) -> tuple[Path, str, Path]:
    candidates = tmp_path / "candidates.csv"
    candidates.write_text(
        "question_id,question_text,forecasted_at,source_cutoff_at,event_id,category\n"
        "123,Will it happen?,2025-02-01T00:00:00Z,2025-02-01T00:00:00Z,e1,test\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(candidates.read_bytes()).hexdigest()
    locators = tmp_path / "locators.jsonl"
    _write_jsonl(
        locators,
        [
            {
                "question_id": "123",
                "locator_status": "success",
                "locator_error": None,
                "locator": _locator(),
            }
        ],
    )
    return candidates, digest, locators


def test_discovery_keeps_no_capture_rows_in_denominator(tmp_path: Path) -> None:
    candidates, digest, locators = _single_candidate_fixture(tmp_path)
    summary = discover_v2_sources(
        candidates_csv=candidates,
        v1_locators_jsonl=locators,
        output_directory=tmp_path / "out",
        providers=[_FakeProvider(capture=False)],
        code_commit="abc",
        candidate_sha256=digest,
        expected_rows=1,
    )
    assert summary["lookup_rows"] == 3
    assert summary["no_capture"] == 3
    assert summary["captures_with_frozen_content"] == 0


def test_discovery_freezes_each_deterministic_pattern(tmp_path: Path) -> None:
    candidates, digest, locators = _single_candidate_fixture(tmp_path)
    summary = discover_v2_sources(
        candidates_csv=candidates,
        v1_locators_jsonl=locators,
        output_directory=tmp_path / "out",
        providers=[_FakeProvider(capture=True)],
        code_commit="abc",
        candidate_sha256=digest,
        expected_rows=1,
    )
    assert summary["lookup_rows"] == 3
    assert summary["captures_with_frozen_content"] == 3
    assert summary["questions_with_capture"] == 1
    assert summary["exact_question_match_diagnostics"] == 3


def test_discovery_rejects_candidate_locator_membership_mismatch(tmp_path: Path) -> None:
    candidates, digest, locators = _single_candidate_fixture(tmp_path)
    rows = _load_rows(locators)
    rows[0]["question_id"] = "999"
    _write_jsonl(locators, rows)
    with pytest.raises(HistoricalSourceV2Error, match="Candidate IDs and V1 locator IDs differ"):
        discover_v2_sources(
            candidates_csv=candidates,
            v1_locators_jsonl=locators,
            output_directory=tmp_path / "out",
            providers=[_FakeProvider(capture=False)],
            code_commit="abc",
            candidate_sha256=digest,
            expected_rows=1,
        )


def _load_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
