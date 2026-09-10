from __future__ import annotations

import io
import json
from pathlib import Path

import httpx
import pandas as pd

from prediction_lab.commoncrawl_evidence import (
    CommonCrawlCapture,
    CommonCrawlClient,
    build_commoncrawl_pilot,
    extract_reference_urls,
    select_parent_event_pilot,
)
from prediction_lab.datasets import freeze_cases
from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter


def test_extract_reference_urls_uses_metadata_only_as_locator() -> None:
    market = {
        "description": "Official project: https://example.org/app. Social: https://x.com/example",
        "resolutionSource": "https://example.org/rules,",
        "events": [{"description": "Mirror https://www.example.org/app"}],
    }
    urls = extract_reference_urls(market)
    assert "https://example.org/app" in urls
    assert "https://x.com/example" in urls
    assert "https://example.org/rules" in urls


def test_parent_event_pilot_is_time_spread_and_one_per_event() -> None:
    rows = []
    for index in range(8):
        rows.append(
            {
                "question_id": f"q{index}",
                "question_text": f"Question {index}",
                "forecasted_at": pd.Timestamp("2025-01-01", tz="UTC")
                + pd.Timedelta(days=index),
                "source_cutoff_at": pd.Timestamp("2025-01-01", tz="UTC")
                + pd.Timedelta(days=index),
                "event_id": f"e{index // 2}",
                "outcome": index % 2,
                "market_probability": 0.99 if index % 2 else 0.01,
            }
        )
    pilot = select_parent_event_pilot(pd.DataFrame(rows), size=3)
    assert len(pilot) == 3
    assert pilot["event_id"].nunique() == 3
    assert "outcome" not in pilot.columns
    assert "market_probability" not in pilot.columns


def test_latest_capture_rejects_post_cutoff_and_non_html() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/collinfo.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "CC-MAIN-2025-43",
                        "from": "2025-10-05T00:00:00",
                        "cdx-api": "https://index.test/CC-MAIN-2025-43-index",
                    }
                ],
            )
        if request.url.path.endswith("-index"):
            rows = [
                {
                    "timestamp": "20251017120000",
                    "url": "https://example.org/",
                    "status": "200",
                    "mime": "text/html",
                    "digest": "FUTURE",
                    "filename": "future.warc.gz",
                    "offset": "1",
                    "length": "2",
                },
                {
                    "timestamp": "20251015120000",
                    "url": "https://example.org/",
                    "status": "200",
                    "mime": "application/pdf",
                    "digest": "PDF",
                    "filename": "pdf.warc.gz",
                    "offset": "1",
                    "length": "2",
                },
                {
                    "timestamp": "20251014120000",
                    "url": "https://example.org/",
                    "status": "200",
                    "mime": "text/html",
                    "digest": "SAFE",
                    "filename": "safe.warc.gz",
                    "offset": "10",
                    "length": "20",
                },
            ]
            return httpx.Response(200, text="\n".join(json.dumps(row) for row in rows))
        raise AssertionError(f"Unexpected URL {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = CommonCrawlClient(client=http_client, index_url="https://index.test")
    capture = client.latest_capture_before(
        "https://example.org/",
        cutoff="2025-10-16T00:00:00Z",
        max_collections=1,
    )
    assert capture is not None
    assert capture.digest == "SAFE"
    assert capture.timestamp == pd.Timestamp("2025-10-14T12:00:00Z")
    http_client.close()


def _warc_bytes() -> bytes:
    stream = io.BytesIO()
    writer = WARCWriter(stream, gzip=True)
    payload = io.BytesIO(
        b"<html><head><title>Archived Title</title><script>bad()</script></head>"
        b"<body><h1>Historical project page</h1><p>Known before the forecast. "
        b"This paragraph is intentionally long enough to pass extraction validation. "
        b"It contains only archived page content from the test fixture.</p>"
        b"<p>Additional historical context makes the body comfortably over two hundred "
        b"characters so the production minimum-text guard does not reject this fixture.</p>"
        b"</body></html>"
    )
    http_headers = StatusAndHeaders("200 OK", [("Content-Type", "text/html")], protocol="HTTP/1.1")
    record = writer.create_warc_record(
        "https://example.org/",
        "response",
        payload=payload,
        http_headers=http_headers,
    )
    writer.write_record(record)
    return stream.getvalue()


def test_fetch_capture_text_parses_archived_warc() -> None:
    warc_payload = _warc_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=0-99"
        return httpx.Response(206, content=warc_payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = CommonCrawlClient(client=http_client, data_url="https://data.test")
    capture = CommonCrawlCapture(
        crawl_id="CC-MAIN-2025-43",
        timestamp=pd.Timestamp("2025-10-14T12:00:00Z"),
        url="https://example.org/",
        digest="DIGEST",
        filename="file.warc.gz",
        offset=0,
        length=100,
        mime="text/html",
        status="200",
    )
    text, title = client.fetch_capture_text(capture)
    assert title == "Archived Title"
    assert "Historical project page" in text
    assert "bad()" not in text
    http_client.close()


def _freeze_development(tmp_path: Path) -> tuple[Path, Path, Path]:
    rows = []
    markets = []
    for index in range(4):
        forecast = pd.Timestamp("2025-10-10T00:00:00Z") + pd.Timedelta(days=index * 10)
        rows.append(
            {
                "question_id": f"q{index}",
                "question_text": f"Will project {index} succeed?",
                "forecasted_at": forecast,
                "resolved_at": forecast + pd.Timedelta(days=30),
                "market_price_timestamp": forecast,
                "source_cutoff_at": forecast,
                "market_probability": 0.5,
                "outcome": index % 2,
                "category": "test",
                "platform": "polymarket",
                "event_id": f"event-{index}",
                "split": "development",
            }
        )
        markets.append(
            {
                "id": f"q{index}",
                "description": f"Official source https://project{index}.example/",
                "events": [],
            }
        )
    csv_path = tmp_path / "development.csv"
    manifest_path = tmp_path / "development.manifest.json"
    freeze_cases(
        pd.DataFrame(rows),
        csv_path=csv_path,
        manifest_path=manifest_path,
        source_name="fixture",
        source_revision="fixture-v1",
        selection_policy="development only",
    )
    markets_path = tmp_path / "source-markets.jsonl"
    markets_path.write_text(
        "".join(json.dumps(item) + "\n" for item in markets),
        encoding="utf-8",
    )
    return csv_path, manifest_path, markets_path


def test_build_pilot_keeps_zero_evidence_questions_explicit(tmp_path: Path) -> None:
    csv_path, manifest_path, markets_path = _freeze_development(tmp_path)

    class FakeClient:
        def latest_capture_before(
            self, url: str, *, cutoff: object, max_collections: int = 6
        ) -> CommonCrawlCapture | None:
            del cutoff, max_collections
            if "project1" in url or "project3" in url:
                return None
            return CommonCrawlCapture(
                crawl_id="CC-MAIN-2025-43",
                timestamp=pd.Timestamp("2025-10-01T00:00:00Z"),
                url=url,
                digest=f"digest-{url}",
                filename="fixture.warc.gz",
                offset=0,
                length=10,
                mime="text/html",
                status="200",
            )

        def fetch_capture_text(
            self, capture: CommonCrawlCapture, *, max_characters: int = 12000
        ) -> tuple[str, str]:
            del max_characters
            return ("Historical evidence " * 20, f"Archived {capture.url}")

    fixture, summary, audit = build_commoncrawl_pilot(
        development_csv=csv_path,
        development_manifest=manifest_path,
        source_markets_jsonl=markets_path,
        client=FakeClient(),  # type: ignore[arg-type]
        pilot_size=4,
    )
    assert summary["questions_with_archived_evidence"] == 2
    assert len(fixture["questions"]) == 4  # type: ignore[arg-type]
    assert fixture["questions"]["q1"] == []  # type: ignore[index]
    assert len(audit) == 4
