from __future__ import annotations

import json

import httpx

from prediction_lab.capture_index_client import (
    CaptureIndexCommonCrawlClient,
    CommonCrawlTransportError,
    canonical_index_key,
)


def test_canonical_index_key_is_scheme_less_and_strips_www() -> None:
    assert (
        canonical_index_key(
            "https://www.example.org/news/specific-article?edition=us"
        )
        == "example.org/news/specific-article?edition=us"
    )


def test_capture_index_uses_one_exact_scheme_less_query_per_collection() -> None:
    queried_urls: list[str] = []
    row = {
        "timestamp": "20260128120000",
        "url": "http://www.example.org/news/specific-article",
        "status": "200",
        "mime": "text/html",
        "digest": "SAFE",
        "filename": "safe.warc.gz",
        "offset": "10",
        "length": "20",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/collinfo.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "CC-MAIN-2026-04",
                        "from": "2026-01-15T00:00:00",
                        "cdx-api": "https://index.test/CC-MAIN-2026-04-index",
                    }
                ],
            )
        if request.url.path.endswith("-index"):
            queried_urls.append(str(request.url.params["url"]))
            assert request.url.params["matchType"] == "exact"
            return httpx.Response(200, text=json.dumps(row))
        raise AssertionError(f"Unexpected URL {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = CaptureIndexCommonCrawlClient(
        client=http_client,
        index_url="https://index.test",
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    capture = client.latest_capture_before(
        "https://example.org/news/specific-article",
        cutoff="2026-01-29T15:41:34Z",
        max_collections=1,
    )
    assert capture is not None
    assert capture.digest == "SAFE"
    assert queried_urls == ["example.org/news/specific-article"]
    http_client.close()


def test_capture_index_rejects_wrong_page_returned_by_provider() -> None:
    wrong_row = {
        "timestamp": "20260128120000",
        "url": "https://example.org/",
        "status": "200",
        "mime": "text/html",
        "digest": "WRONG",
        "filename": "wrong.warc.gz",
        "offset": "10",
        "length": "20",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/collinfo.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "CC-MAIN-2026-04",
                        "from": "2026-01-15T00:00:00",
                        "cdx-api": "https://index.test/CC-MAIN-2026-04-index",
                    }
                ],
            )
        if request.url.path.endswith("-index"):
            return httpx.Response(200, text=json.dumps(wrong_row))
        raise AssertionError(f"Unexpected URL {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = CaptureIndexCommonCrawlClient(
        client=http_client,
        index_url="https://index.test",
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    capture = client.latest_capture_before(
        "https://example.org/news/specific-article",
        cutoff="2026-01-29T15:41:34Z",
        max_collections=1,
    )
    assert capture is None
    http_client.close()


def test_capture_index_surfaces_transport_failure_after_retries() -> None:
    index_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal index_calls
        if request.url.path.endswith("/collinfo.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "CC-MAIN-2026-04",
                        "from": "2026-01-15T00:00:00",
                        "cdx-api": "https://index.test/CC-MAIN-2026-04-index",
                    }
                ],
            )
        if request.url.path.endswith("-index"):
            index_calls += 1
            return httpx.Response(503, text="temporary")
        raise AssertionError(f"Unexpected URL {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = CaptureIndexCommonCrawlClient(
        client=http_client,
        index_url="https://index.test",
        retries=2,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    try:
        client.latest_capture_before(
            "https://example.org/news/specific-article",
            cutoff="2026-01-29T15:41:34Z",
            max_collections=1,
        )
    except CommonCrawlTransportError:
        pass
    else:
        raise AssertionError("Expected transport failure")
    assert index_calls == 2
    http_client.close()


def test_capture_index_client_error_is_incomplete_not_fatal() -> None:
    queried_collections: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/collinfo.json"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "CC-MAIN-2026-08",
                        "from": "2026-02-01T00:00:00",
                        "cdx-api": "https://index.test/CC-MAIN-2026-08-index",
                    },
                    {
                        "id": "CC-MAIN-2026-04",
                        "from": "2026-01-01T00:00:00",
                        "cdx-api": "https://index.test/CC-MAIN-2026-04-index",
                    },
                ],
            )
        if request.url.path.endswith("CC-MAIN-2026-08-index"):
            queried_collections.append("08")
            return httpx.Response(400, text='{"message":"provider could not service query"}')
        if request.url.path.endswith("CC-MAIN-2026-04-index"):
            queried_collections.append("04")
            return httpx.Response(404, json={"message": "No Captures found"})
        raise AssertionError(f"Unexpected URL {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = CaptureIndexCommonCrawlClient(
        client=http_client,
        index_url="https://index.test",
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    try:
        client.latest_capture_before(
            "https://example.org/news/specific-article",
            cutoff="2026-03-01T00:00:00Z",
            max_collections=2,
        )
    except CommonCrawlTransportError as exc:
        assert "HTTP 400" in str(exc)
        assert "provider could not service query" in str(exc)
    else:
        raise AssertionError("Expected incomplete lookup to remain retryable")
    assert queried_collections == ["08", "04"]
    http_client.close()
