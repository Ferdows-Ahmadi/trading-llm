from __future__ import annotations

import json

import httpx
import pandas as pd

from prediction_lab.gdelt_evidence import (
    FastCommonCrawlClient,
    GdeltDocClient,
    build_gdelt_query,
)


def test_gdelt_query_anchors_niche_crypto_entity_without_threshold_terms() -> None:
    query = build_gdelt_query("Hyperswap FDV above $500M one day after launch?")
    assert query.startswith("Hyperswap ")
    assert "token OR crypto OR blockchain" in query
    assert "500M" not in query
    assert "FDV" not in query


def test_gdelt_query_keeps_major_crypto_asset_broad() -> None:
    query = build_gdelt_query("Will Ethereum dip to $2,000 by December 31, 2026?")
    assert query == "Ethereum"


def test_gdelt_retries_429_without_real_sleep() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"articles": []})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = GdeltDocClient(
        client=http_client,
        endpoint="https://gdelt.test/doc",
        retries=2,
        retry_backoff_seconds=0,
        minimum_interval_seconds=0,
    )
    articles = client.search(
        "Will Ethereum dip to $2,000 by December 31, 2026?",
        cutoff=pd.Timestamp("2026-01-29T15:41:34Z"),
        lookback_days=45,
        max_records=20,
    )
    assert articles == []
    assert requests == 2
    http_client.close()


def test_fast_commoncrawl_never_degrades_article_lookup_to_homepage() -> None:
    queried_urls: list[str] = []

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
            return httpx.Response(200, text="")
        raise AssertionError(f"Unexpected URL {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = FastCommonCrawlClient(client=http_client, index_url="https://index.test")
    capture = client.latest_capture_before(
        "https://www.example.org/news/specific-article",
        cutoff="2026-01-29T15:41:34Z",
        max_collections=1,
    )
    assert capture is None
    assert queried_urls
    assert all("/news/specific-article" in value for value in queried_urls)
    roots = {"https://example.org", "https://www.example.org"}
    assert all(value.rstrip("/") not in roots for value in queried_urls)
    http_client.close()


def test_fast_commoncrawl_continues_after_transient_variant_failure() -> None:
    index_calls = 0
    row = {
        "timestamp": "20260128120000",
        "url": "http://example.org/news/article",
        "status": "200",
        "mime": "text/html",
        "digest": "SAFE",
        "filename": "safe.warc.gz",
        "offset": "10",
        "length": "20",
    }

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
            if index_calls == 1:
                return httpx.Response(503, text="temporary")
            return httpx.Response(200, text=json.dumps(row))
        raise AssertionError(f"Unexpected URL {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = FastCommonCrawlClient(
        client=http_client,
        index_url="https://index.test",
        retries=1,
        retry_backoff_seconds=0,
    )
    capture = client.latest_capture_before(
        "https://example.org/news/article",
        cutoff="2026-01-29T15:41:34Z",
        max_collections=1,
    )
    assert capture is not None
    assert capture.digest == "SAFE"
    assert index_calls >= 2
    http_client.close()
