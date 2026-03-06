from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.news_context.service import NewsIngestionSummary, get_news_context_service
from app.repositories.news_context_repository import FeedNewsRow


class _FakeNewsService:
    def provider_codes(self) -> list[str]:
        return ["alpha_vantage"]

    def ingest_news(self, **kwargs) -> NewsIngestionSummary:  # type: ignore[no-untyped-def]
        _ = kwargs
        return NewsIngestionSummary(
            provider_code="alpha_vantage",
            fetched_count=10,
            inserted_count=6,
            updated_count=2,
            deduplicated_count=2,
            tagged_links_count=8,
            duration_ms=120,
        )

    def list_feed(self, **kwargs) -> list[FeedNewsRow]:  # type: ignore[no-untyped-def]
        _ = kwargs
        return [
            FeedNewsRow(
                id="id-1",
                title="BTC rallies as macro risk eases",
                summary="Summary",
                url="https://example.com/feed-1",
                source_name="Desk",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                sentiment_label="positive",
                importance_score=72.2,
                asset_symbols=["BTCUSDT"],
                contradiction_signals=[
                    {
                        "asset_symbol": "BTCUSDT",
                        "price_change_pct_24h": -1.9,
                        "is_contradiction": True,
                    }
                ],
            )
        ]


def test_news_endpoints() -> None:
    app.dependency_overrides[get_news_context_service] = lambda: _FakeNewsService()
    client = TestClient(app)

    providers_response = client.get("/api/v1/news/providers")
    ingest_response = client.post("/api/v1/news/ingest", json={"provider_code": "alpha_vantage", "limit": 10})
    feed_response = client.get("/api/v1/news/feed?limit=5&hours=24")
    app.dependency_overrides.clear()

    assert providers_response.status_code == 200
    assert providers_response.json() == ["alpha_vantage"]
    assert ingest_response.status_code == 200
    assert ingest_response.json()["inserted_count"] == 6
    assert feed_response.status_code == 200
    assert feed_response.json()["items"][0]["contradiction_signals"][0]["is_contradiction"] is True
