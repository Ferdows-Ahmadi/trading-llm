from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from prediction_lab.prospective_live_rss_v01 import (
    CAPTURE_WINDOW_SECONDS,
    GoogleNewsRssClient,
    LiveCaptureError,
    bind_market_snapshot,
    capture_question,
    parse_rss_items,
)

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss><channel>
<item><title>Alpha update</title><link>https://example.com/a</link>
<pubDate>Tue, 15 Sep 2026 01:00:00 GMT</pubDate>
<description><![CDATA[<b>Useful</b> context]]></description><source>Example</source></item>
<item><title>Beta update</title><link>https://example.com/b</link>
<description>Second item</description></item>
</channel></rss>
"""


def test_parse_rss_items_is_bounded_and_cleans_description() -> None:
    items = parse_rss_items(RSS, max_items=1)
    assert len(items) == 1
    assert items[0].title == "Alpha update"
    assert items[0].description == "Useful context"


def test_capture_question_freezes_raw_and_terminal_manifest(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RSS, request=request)

    client = GoogleNewsRssClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retries=1,
        retry_backoff_seconds=0,
    )
    stamps = iter(
        [
            datetime(2026, 9, 15, 1, 0, tzinfo=UTC),
            datetime(2026, 9, 15, 1, 0, 4, tzinfo=UTC),
        ]
    )
    manifest = capture_question(
        question_id="polymarket-market:1",
        question_text="Will alpha happen?",
        output_directory=tmp_path,
        client=client,
        clock=lambda: next(stamps),
    )
    assert manifest["status"] == "verified_complete"
    assert manifest["evidence_items"] == 2
    row_dirs = list(tmp_path.iterdir())
    assert len(row_dirs) == 1
    assert (row_dirs[0] / "raw-google-news-rss.xml").read_bytes() == RSS
    assert (row_dirs[0] / "capture-manifest.json").exists()


def test_successful_empty_feed_is_verified_empty(tmp_path: Path) -> None:
    empty = b"<?xml version='1.0'?><rss><channel></channel></rss>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=empty, request=request)

    client = GoogleNewsRssClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retries=1,
        retry_backoff_seconds=0,
    )
    stamps = iter(
        [
            datetime(2026, 9, 15, 1, 0, tzinfo=UTC),
            datetime(2026, 9, 15, 1, 0, 1, tzinfo=UTC),
        ]
    )
    manifest = capture_question(
        question_id="polymarket-market:2",
        question_text="Will beta happen?",
        output_directory=tmp_path,
        client=client,
        clock=lambda: next(stamps),
    )
    assert manifest["status"] == "verified_empty"
    assert manifest["evidence_items"] == 0


def test_provider_failure_remains_retrieval_failure(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    client = GoogleNewsRssClient(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retries=1,
        retry_backoff_seconds=0,
    )
    stamps = iter(
        [
            datetime(2026, 9, 15, 1, 0, tzinfo=UTC),
            datetime(2026, 9, 15, 1, 0, 2, tzinfo=UTC),
        ]
    )
    manifest = capture_question(
        question_id="polymarket-market:3",
        question_text="Will gamma happen?",
        output_directory=tmp_path,
        client=client,
        clock=lambda: next(stamps),
    )
    assert manifest["status"] == "retrieval_failure"


def test_market_snapshot_must_follow_capture_and_stay_inside_window() -> None:
    manifest = {
        "status": "verified_complete",
        "capture_started_at": "2026-09-15T01:00:00Z",
        "capture_completed_at": "2026-09-15T01:02:00Z",
    }
    bound = bind_market_snapshot(
        manifest,
        market_price_timestamp="2026-09-15T01:03:00Z",
    )
    assert bound["market_snapshot_bound"] is True

    with pytest.raises(LiveCaptureError):
        bind_market_snapshot(
            manifest,
            market_price_timestamp="2026-09-15T00:59:59Z",
        )

    too_late = datetime(2026, 9, 15, 1, 0, tzinfo=UTC) + timedelta(
        seconds=CAPTURE_WINDOW_SECONDS + 1
    )
    with pytest.raises(LiveCaptureError):
        bind_market_snapshot(
            manifest,
            market_price_timestamp=too_late.isoformat(),
        )
