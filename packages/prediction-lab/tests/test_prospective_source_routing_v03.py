from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from prediction_lab import prospective_source_routing_v03 as routing


RAW_RSS = b"""<?xml version='1.0' encoding='UTF-8'?>
<rss><channel><item>
<title>Baseline headline</title>
<link>https://news.example/item</link>
<source>Example News</source>
<pubDate>Thu, 17 Sep 2026 06:00:00 GMT</pubDate>
<description>Baseline RSS evidence</description>
</item></channel></rss>"""


class FakeRss:
    def search(self, question_text: str) -> tuple[bytes, str]:
        assert question_text == "Will X happen?"
        return RAW_RSS, "https://news.google.com/rss/search?q=x"


def _ticks() -> object:
    values = iter(
        [
            datetime(2026, 9, 17, 6, 0, 0, tzinfo=UTC),
            datetime(2026, 9, 17, 6, 0, 1, tzinfo=UTC),
        ]
    )
    return lambda: next(values)


def test_resolution_url_filter_is_ordered_bounded_and_rejects_unsafe() -> None:
    urls = routing.valid_resolution_urls(
        [
            "not a url",
            "file:///tmp/nope",
            "http://127.0.0.1/private",
            "https://example.com/one",
            "https://example.com/one",
            "https://example.org/two",
            "https://third.example/three",
        ]
    )
    assert urls == ["https://example.com/one", "https://example.org/two"]


def test_direct_resolution_source_success_augments_only_condition_b(tmp_path) -> None:
    source_body = (
        b"<html><body><h1>Official resolution source</h1>"
        b"<p>This official page contains enough deterministic evidence text for the market. "
        b"It is intentionally longer than one hundred characters so it is admitted.</p></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://official.example/status"
        return httpx.Response(
            200,
            content=source_body,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    source_client = routing.ResolutionSourceClient(client=http, retries=1)
    manifest = routing.capture_paired_evidence(
        question_id="polymarket-market:1",
        question_text="Will X happen?",
        resolution_sources=["https://official.example/status"],
        output_directory=tmp_path,
        rss_client=FakeRss(),  # type: ignore[arg-type]
        source_client=source_client,
        clock=_ticks(),  # type: ignore[arg-type]
    )
    assert manifest["status"] == "verified_complete"
    assert manifest["direct_source_attempts"] == 1
    assert manifest["direct_source_successes"] == 1
    assert manifest["condition_a_evidence_items"] == 1
    assert manifest["condition_b_evidence_items"] == 2

    row = tmp_path / routing._safe_name("polymarket-market:1")
    condition_a = json.loads((row / "condition-a-evidence.json").read_text(encoding="utf-8"))
    condition_b = json.loads((row / "condition-b-evidence.json").read_text(encoding="utf-8"))
    assert condition_b[0] == condition_a[0]
    assert condition_b[1]["source_type"] == "contract-resolution-source"
    assert "Official resolution source" in condition_b[1]["text"]
    source_client.close()
    http.close()


def test_direct_source_failure_preserves_exact_rss_fallback(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    source_client = routing.ResolutionSourceClient(client=http, retries=1)
    manifest = routing.capture_paired_evidence(
        question_id="polymarket-market:2",
        question_text="Will X happen?",
        resolution_sources=["https://blocked.example/source"],
        output_directory=tmp_path,
        rss_client=FakeRss(),  # type: ignore[arg-type]
        source_client=source_client,
        clock=_ticks(),  # type: ignore[arg-type]
    )
    assert manifest["status"] == "verified_complete"
    assert manifest["direct_source_attempts"] == 1
    assert manifest["direct_source_successes"] == 0
    row = tmp_path / routing._safe_name("polymarket-market:2")
    condition_a = (row / "condition-a-evidence.json").read_bytes()
    condition_b = (row / "condition-b-evidence.json").read_bytes()
    assert condition_b == condition_a
    source_client.close()
    http.close()


def test_malformed_and_non_http_locators_are_recorded_but_not_fetched(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected fetch: {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    source_client = routing.ResolutionSourceClient(client=http, retries=1)
    manifest = routing.capture_paired_evidence(
        question_id="polymarket-market:3",
        question_text="Will X happen?",
        resolution_sources=["arena.ai leaderboard", "mailto:test@example.com", ""],
        output_directory=tmp_path,
        rss_client=FakeRss(),  # type: ignore[arg-type]
        source_client=source_client,
        clock=_ticks(),  # type: ignore[arg-type]
    )
    assert manifest["valid_resolution_urls"] == []
    assert manifest["direct_source_attempts"] == 0
    assert manifest["resolution_source_locators"] == [
        "arena.ai leaderboard",
        "mailto:test@example.com",
        "",
    ]
    source_client.close()
    http.close()


def test_capture_refuses_to_replace_existing_row(tmp_path) -> None:
    http = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(403, request=request)),
        follow_redirects=False,
    )
    source_client = routing.ResolutionSourceClient(client=http, retries=1)
    kwargs = {
        "question_id": "polymarket-market:4",
        "question_text": "Will X happen?",
        "resolution_sources": [],
        "output_directory": tmp_path,
        "rss_client": FakeRss(),
        "source_client": source_client,
    }
    routing.capture_paired_evidence(**kwargs, clock=_ticks())  # type: ignore[arg-type]
    with pytest.raises(routing.SourceRoutingError, match="Refusing to replace"):
        routing.capture_paired_evidence(**kwargs, clock=_ticks())  # type: ignore[arg-type]
    source_client.close()
    http.close()
