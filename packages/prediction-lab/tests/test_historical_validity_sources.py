from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from prediction_lab import historical_validity_sources as sources
from prediction_lab.research_types import ResearchContractError


class FakeLocator:
    def __init__(self, payload: dict[str, object] | None = None, *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail

    def fetch_market(self, market_id: str) -> dict[str, object]:
        if self.fail:
            raise sources.SourceTransportError("locator down")
        assert self.payload is not None
        return self.payload


class FakeCdx:
    def __init__(self, capture: sources.AuditCapture | None = None, *, fail: bool = False) -> None:
        self.capture = capture
        self.fail = fail
        self.urls: list[str] = []

    def latest_capture_before(self, url: str, *, cutoff: object) -> sources.AuditCapture | None:
        del cutoff
        self.urls.append(url)
        if self.fail:
            raise sources.SourceTransportError("cdx down")
        return self.capture


class FakeReplay:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.urls: list[str] = []

    def fetch(self, replay_url: str) -> httpx.Response:
        self.urls.append(replay_url)
        return self.response


def _write_candidate(tmp_path: Path, *, question: str = "Test question?") -> Path:
    path = tmp_path / "candidates.csv"
    frame = pd.DataFrame(
        [
            {
                "question_id": "123",
                "question_text": question,
                "forecasted_at": "2026-01-10T00:00:00.000000Z",
                "source_cutoff_at": "2026-01-10T00:00:00.000000Z",
                "event_id": "polymarket-event:1",
                "category": "crypto",
            }
        ]
    )
    frame.to_csv(path, index=False, lineterminator="\n")
    return path


def _bind_candidate(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(sources, "CANDIDATE_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(sources, "CANDIDATE_ROWS", 1)


def _locator() -> dict[str, object]:
    return {
        "market": {
            "id": "123",
            "question": "Test question?",
            "slug": "test-question",
            "description": "Rules",
        },
        "events": [{"id": "1", "slug": "test-event", "title": "Test Event"}],
    }


def test_locator_redaction_excludes_price_and_outcome_fields() -> None:
    raw = {
        "id": "123",
        "question": "Q?",
        "slug": "q",
        "outcomePrices": '["1", "0"]',
        "volume": "100000",
        "events": [{"id": "1", "slug": "event", "title": "E", "volume": 50}],
    }
    redacted = sources._redact_locator(raw, market_id="123")
    serialized = json.dumps(redacted)
    assert "outcomePrices" not in serialized
    assert "volume" not in serialized
    assert redacted["market"]["question"] == "Q?"


def test_locator_urls_are_frozen_patterns() -> None:
    assert sources.locator_urls("123", _locator()) == [
        ("gamma-direct", "https://gamma-api.polymarket.com/markets/123"),
        ("gamma-query", "https://gamma-api.polymarket.com/markets?id=123"),
        ("event:test-event", "https://polymarket.com/event/test-event"),
    ]


def test_same_logical_url_requires_query_equality() -> None:
    assert sources.same_logical_url(
        "https://gamma-api.polymarket.com/markets?id=123",
        "http://www.gamma-api.polymarket.com/markets?id=123",
    )
    assert not sources.same_logical_url(
        "https://gamma-api.polymarket.com/markets?id=123",
        "https://gamma-api.polymarket.com/markets?id=456",
    )
    assert not sources.same_logical_url(
        "https://polymarket.com/event/test",
        "https://polymarket.com/event/test?foo=bar",
    )


def test_discovery_keeps_candidate_when_locator_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _write_candidate(tmp_path)
    _bind_candidate(monkeypatch, candidate)
    output = tmp_path / "output"
    summary = sources.discover_sources(
        candidates_csv=candidate,
        output_directory=output,
        locator_client=FakeLocator(fail=True),
        cdx_client=FakeCdx(),
        replay_client=FakeReplay(httpx.Response(200, content=b"unused")),
        code_commit="a" * 40,
    )
    locators = [json.loads(line) for line in (output / "locators.jsonl").read_text().splitlines()]
    assert len(locators) == 1
    assert locators[0]["locator_status"] == "failure"
    assert summary["candidate_rows"] == 1
    assert summary["url_patterns_attempted"] == 0


def test_json_capture_freeze_records_exact_question_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _write_candidate(tmp_path)
    _bind_candidate(monkeypatch, candidate)
    capture = sources.AuditCapture(
        timestamp=pd.Timestamp("2026-01-09T00:00:00Z"),
        original="https://gamma-api.polymarket.com/markets/123",
        mime="application/json",
        status="200",
        digest="archive-digest",
        length=100,
        replay_url="https://web.archive.org/web/20260109000000id_/https://gamma-api.polymarket.com/markets/123",
    )
    response = httpx.Response(
        200,
        json={"id": "123", "question": "Test question?", "description": "Historical rules"},
        request=httpx.Request("GET", capture.replay_url),
    )
    output = tmp_path / "output"
    summary = sources.discover_sources(
        candidates_csv=candidate,
        output_directory=output,
        locator_client=FakeLocator(_locator()),
        cdx_client=FakeCdx(capture),
        replay_client=FakeReplay(response),
        code_commit="b" * 40,
    )
    lookups = [
        json.loads(line) for line in (output / "wayback-lookups.jsonl").read_text().splitlines()
    ]
    assert len(lookups) == 3
    assert all(row["lookup_status"] == "capture" for row in lookups)
    assert all(row["replay"]["benchmark_question_exact_match"] is True for row in lookups)
    assert summary["exact_question_match_diagnostics"] == 3
    assert summary["captures_with_frozen_replay"] == 3


def test_candidate_tampering_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = _write_candidate(tmp_path)
    _bind_candidate(monkeypatch, candidate)
    candidate.write_text(candidate.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ResearchContractError, match="digest changed"):
        sources.discover_sources(
            candidates_csv=candidate,
            output_directory=tmp_path / "output",
            locator_client=FakeLocator(_locator()),
            cdx_client=FakeCdx(),
            replay_client=FakeReplay(httpx.Response(200)),
            code_commit="c" * 40,
        )
