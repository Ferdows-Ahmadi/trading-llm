from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.wayback_content import (
    WaybackContentError,
    WaybackReplayClient,
    extract_archived_html_text,
    freeze_wayback_content,
)


def test_extract_archived_html_text_skips_script_and_style() -> None:
    text = extract_archived_html_text(
        """
        <html><head><style>.x{display:none}</style></head>
        <body><article><h1>Historical headline</h1><p>Useful evidence.</p>
        <script>futureLeak()</script></article></body></html>
        """
    )
    assert "Historical headline" in text
    assert "Useful evidence." in text
    assert "futureLeak" not in text
    assert "display:none" not in text


def test_replay_client_refuses_redirect_from_exact_snapshot() -> None:
    replay = "https://web.archive.org/web/20260102120000id_/https://example.org/a"
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                302,
                headers={"Location": "https://example.org/a"},
                request=request,
            )
        ),
        follow_redirects=False,
    )
    client = WaybackReplayClient(
        client=http_client,
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    with pytest.raises(WaybackContentError, match="redirected"):
        client.fetch(replay)
    http_client.close()


def test_replay_client_refuses_non_wayback_replay_url() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    client = WaybackReplayClient(
        client=http_client,
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    with pytest.raises(WaybackContentError, match="Unsafe Wayback replay URL"):
        client.fetch("https://example.org/article")
    http_client.close()


def test_freeze_wayback_content_builds_hashed_evidence_fixture(tmp_path: Path) -> None:
    replay = "https://web.archive.org/web/20260102120000id_/https://example.org/a"
    capture = {
        "article_title": "Historical article",
        "article_url": "https://example.org/a",
        "capture": {
            "digest": "ARCHIVE-DIGEST",
            "replay_url": replay,
            "timestamp": "2026-01-02T12:00:00+00:00",
            "url": "https://example.org/a",
        },
        "capture_found": True,
        "event_id": "event-1",
        "lookup_status": "capture",
        "question_id": "q1",
        "source_cutoff_at": "2026-01-03T00:00:00+00:00",
    }
    capture_path = tmp_path / "captures.jsonl"
    capture_path.write_text(json.dumps(capture) + "\n", encoding="utf-8")

    html = "<html><body><article><h1>Historical article</h1><p>" + ("evidence " * 40) + "</p></article></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=html,
            headers={"Content-Type": "text/html; charset=utf-8"},
            request=request,
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    replay_client = WaybackReplayClient(
        client=http_client,
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    output = tmp_path / "frozen"
    summary = freeze_wayback_content(
        captures_jsonl=capture_path,
        output_directory=output,
        replay_client=replay_client,
        max_items_per_question=1,
        minimum_text_chars=100,
    )

    assert summary["frozen_items"] == 1
    assert summary["content_failures"] == 0
    fixture = json.loads((output / "evidence-fixture.json").read_text(encoding="utf-8"))
    item = fixture["questions"]["q1"][0]
    assert item["available_at"] == "2026-01-02T12:00:00.000000Z"
    assert item["source_type"] == "wayback-archived-news"
    assert item["text"]
    assert (output / "raw").glob("*.html")
    assert (output / "text").glob("*.txt")

    provider = FileEvidenceProvider(output / "evidence-fixture.json")
    packet = provider.build_packet(
        question_id="q1",
        forecasted_at="2026-01-03T00:00:00Z",
        research_cutoff_at="2026-01-03T00:00:00Z",
    )
    assert len(packet.evidence_items) == 1
    assert packet.evidence_items[0].available_at.isoformat() == "2026-01-02T12:00:00+00:00"
    http_client.close()


def test_freeze_wayback_content_rejects_post_cutoff_capture(tmp_path: Path) -> None:
    capture = {
        "article_title": "Unsafe article",
        "article_url": "https://example.org/a",
        "capture": {
            "digest": "ARCHIVE-DIGEST",
            "replay_url": "https://web.archive.org/web/20260104120000id_/https://example.org/a",
            "timestamp": "2026-01-04T12:00:00+00:00",
            "url": "https://example.org/a",
        },
        "capture_found": True,
        "event_id": "event-1",
        "lookup_status": "capture",
        "question_id": "q1",
        "source_cutoff_at": "2026-01-03T00:00:00+00:00",
    }
    capture_path = tmp_path / "captures.jsonl"
    capture_path.write_text(json.dumps(capture) + "\n", encoding="utf-8")
    http_client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    replay_client = WaybackReplayClient(client=http_client, minimum_interval_seconds=0)

    with pytest.raises(WaybackContentError, match="Post-cutoff"):
        freeze_wayback_content(
            captures_jsonl=capture_path,
            output_directory=tmp_path / "frozen",
            replay_client=replay_client,
        )
    http_client.close()
