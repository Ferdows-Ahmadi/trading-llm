from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.news_context.adapters.base import NewsProviderAdapter
from app.news_context.adapters.registry import NewsAdapterRegistry
from app.news_context.domain import NewsCandidate
from app.news_context.service import NewsContextService
from app.repositories.news_context_repository import AssetRef, FeedNewsRow, ProviderRef, StoredNewsItem


class _FakeAdapter(NewsProviderAdapter):
    provider_code = "alpha_vantage"

    def fetch_news(self, *, limit: int, symbols: list[str] | None = None) -> list[NewsCandidate]:
        _ = symbols
        base_candidate = NewsCandidate(
            external_id="n1",
            source_name="Desk",
            title="BTC rallies on risk appetite",
            summary="Bullish move continues for BTC.",
            url="https://example.com/n1",
            published_at=datetime(2026, 1, 1, 10, 15, tzinfo=UTC),
            provider_tickers=["BTC"],
        )
        duplicate = NewsCandidate(
            external_id="n2",
            source_name="Desk",
            title="BTC   rallies on risk appetite!!!",
            summary="same headline",
            url="https://example.com/n2",
            published_at=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
            provider_tickers=["BTC"],
        )
        return [base_candidate, duplicate][:limit]


class _FakeRepository:
    def __init__(self) -> None:
        self.items: dict[str, StoredNewsItem] = {}
        self.links: list[tuple[str, str, float]] = []

    def get_or_create_provider(self, provider_code: str) -> ProviderRef:
        return ProviderRef(id=uuid.uuid4(), code=provider_code, rate_limit_per_minute=5)

    def list_assets(self) -> list[AssetRef]:
        return [
            AssetRef(
                id=uuid.uuid4(),
                normalized_symbol="BTCUSDT",
                base_currency="BTC",
                quote_currency="USDT",
                display_symbol="BTC/USDT",
                asset_class="crypto",
            )
        ]

    def upsert_news_item(self, **kwargs):  # type: ignore[no-untyped-def]
        dedup_key = kwargs["dedup_key"]
        created = dedup_key not in self.items
        item_id = uuid.uuid4()
        stored = StoredNewsItem(
            id=item_id,
            title=kwargs["title"],
            summary=kwargs["summary"],
            url=kwargs["url"],
            source_name=kwargs["source_name"],
            published_at=kwargs["published_at"],
            sentiment_label=kwargs["sentiment_label"],
            importance_score=kwargs["importance_score"],
            dedup_key=dedup_key,
            metadata=kwargs["metadata"],
        )
        self.items[dedup_key] = stored
        return (stored, created)

    def upsert_news_asset_link(self, **kwargs):  # type: ignore[no-untyped-def]
        self.links.append(
            (
                str(kwargs["news_item_id"]),
                str(kwargs["asset_id"]),
                float(kwargs["relevance_score"]),
            )
        )

    def list_news_feed(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return [
            FeedNewsRow(
                id="item-1",
                title="BTC rallies on risk appetite",
                summary="Summary",
                url="https://example.com/n1",
                source_name="Desk",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                sentiment_label="positive",
                importance_score=70.0,
                asset_symbols=["BTCUSDT"],
                contradiction_signals=[],
            )
        ]


def test_news_service_ingest_with_dedup() -> None:
    service = NewsContextService(
        repository=_FakeRepository(),  # type: ignore[arg-type]
        adapter_registry=NewsAdapterRegistry([_FakeAdapter()]),
    )

    summary = service.ingest_news(provider_code="alpha_vantage", limit=5, symbols=["BTCUSDT"], asset_class="crypto")
    assert summary.fetched_count == 2
    assert summary.inserted_count == 1
    assert summary.deduplicated_count == 1


def test_news_service_feed() -> None:
    service = NewsContextService(
        repository=_FakeRepository(),  # type: ignore[arg-type]
        adapter_registry=NewsAdapterRegistry([_FakeAdapter()]),
    )
    feed = service.list_feed(limit=10, hours=48, symbol=None, asset_class=None)
    assert len(feed) == 1
