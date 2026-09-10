from __future__ import annotations

import httpx
import pandas as pd

from prediction_lab.gdelt_evidence import GdeltDocClient, build_gdelt_query


def test_build_gdelt_query_uses_question_terms_only() -> None:
    query = build_gdelt_query("Will Bitcoin close above $100,000 before December 2025?")
    assert query == "Bitcoin"
    assert "will" not in query.lower()
    assert "100" not in query
    assert "December" not in query


def test_gdelt_search_discards_post_cutoff_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["enddatetime"] == "20251001120000"
        return httpx.Response(
            200,
            json={
                "articles": [
                    {
                        "title": "Historical item",
                        "url": "https://example.com/old",
                        "seendate": "20251001T110000Z",
                        "domain": "example.com",
                        "language": "English",
                        "sourcecountry": "United States",
                    },
                    {
                        "title": "Future item",
                        "url": "https://example.com/future",
                        "seendate": "20251001T130000Z",
                        "domain": "example.com",
                        "language": "English",
                        "sourcecountry": "United States",
                    },
                ]
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = GdeltDocClient(client=http_client)
    articles = client.search(
        "Will Bitcoin exceed 100000 in October 2025?",
        cutoff=pd.Timestamp("2025-10-01T12:00:00Z"),
        lookback_days=30,
        max_records=10,
    )

    assert [article.url for article in articles] == ["https://example.com/old"]
    assert articles[0].seen_at == pd.Timestamp("2025-10-01T11:00:00Z")
    http_client.close()
