from __future__ import annotations

import httpx
import pytest

from prediction_lab.wayback_capture_client import (
    WaybackCdxClient,
    WaybackTransportError,
    same_exact_page,
)


def test_same_exact_page_allows_scheme_and_www_variation() -> None:
    assert same_exact_page(
        "https://www.example.org/news/article",
        "http://example.org/news/article",
    )
    assert not same_exact_page(
        "https://example.org/news/article",
        "https://example.org/",
    )


def test_wayback_selects_latest_valid_pre_cutoff_capture() -> None:
    payload = [
        ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
        [
            "20260102100000",
            "http://example.org/news/article",
            "text/html",
            "200",
            "OLDER",
            "100",
        ],
        [
            "20260103100000",
            "https://www.example.org/news/article",
            "text/html",
            "200",
            "LATEST",
            "120",
        ],
        [
            "20260105100000",
            "https://example.org/news/article",
            "text/html",
            "200",
            "TOO_LATE",
            "130",
        ],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["url"] == "https://example.org/news/article"
        assert request.url.params["matchType"] == "exact"
        return httpx.Response(200, json=payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = WaybackCdxClient(
        client=http_client,
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    capture = client.latest_capture_before(
        "https://example.org/news/article",
        cutoff="2026-01-04T00:00:00Z",
    )
    assert capture is not None
    assert capture.digest == "LATEST"
    assert capture.length == 120
    assert capture.timestamp.isoformat() == "2026-01-03T10:00:00+00:00"
    http_client.close()


def test_wayback_rejects_different_page_from_provider() -> None:
    payload = [
        ["timestamp", "original", "mimetype", "statuscode", "digest", "length"],
        [
            "20260102100000",
            "https://example.org/",
            "text/html",
            "200",
            "WRONG",
            "100",
        ],
    ]

    http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    client = WaybackCdxClient(
        client=http_client,
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    assert (
        client.latest_capture_before(
            "https://example.org/news/article",
            cutoff="2026-01-04T00:00:00Z",
        )
        is None
    )
    http_client.close()


def test_wayback_surfaces_server_failure_after_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="temporary")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = WaybackCdxClient(
        client=http_client,
        retries=2,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    with pytest.raises(WaybackTransportError):
        client.latest_capture_before(
            "https://example.org/news/article",
            cutoff="2026-01-04T00:00:00Z",
        )
    assert calls == 2
    http_client.close()


def test_wayback_treats_unexpected_client_error_as_inconclusive() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(400, text="bad request")
        )
    )
    client = WaybackCdxClient(
        client=http_client,
        retries=1,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    with pytest.raises(WaybackTransportError):
        client.latest_capture_before(
            "https://example.org/news/article",
            cutoff="2026-01-04T00:00:00Z",
        )
    http_client.close()
