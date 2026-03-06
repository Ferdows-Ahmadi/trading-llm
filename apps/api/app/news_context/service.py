from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import cast
from uuid import UUID

from app.core.config import settings
from app.market_data.domain import AssetClass
from app.market_data.exceptions import SymbolNormalizationError
from app.market_data.normalization import normalize_symbol
from app.news_context.adapters.registry import NewsAdapterRegistry, build_news_registry
from app.news_context.deduplication import build_dedup_key
from app.news_context.domain import TaggedAsset
from app.news_context.exceptions import NewsContextError
from app.news_context.scoring import score_importance
from app.news_context.sentiment import label_sentiment
from app.news_context.tagging import tag_assets
from app.repositories.base import SessionLocal
from app.repositories.news_context_repository import FeedNewsRow, NewsContextRepository


@dataclass(frozen=True)
class NewsIngestionSummary:
    provider_code: str
    fetched_count: int
    inserted_count: int
    updated_count: int
    deduplicated_count: int
    tagged_links_count: int
    duration_ms: int


class NewsContextService:
    def __init__(self, repository: NewsContextRepository, adapter_registry: NewsAdapterRegistry) -> None:
        self._repository = repository
        self._adapter_registry = adapter_registry

    def ingest_news(
        self,
        *,
        provider_code: str,
        limit: int,
        symbols: list[str] | None,
        asset_class: str | None,
    ) -> NewsIngestionSummary:
        started = perf_counter()
        provider = self._repository.get_or_create_provider(provider_code)
        adapter = self._adapter_registry.get(provider_code)

        try:
            symbol_filters = _normalize_symbol_filters(symbols=symbols, asset_class=asset_class)
        except SymbolNormalizationError as exc:
            raise NewsContextError(str(exc)) from exc
        candidates = adapter.fetch_news(limit=limit, symbols=symbol_filters if symbol_filters else None)
        assets = self._repository.list_assets()

        inserted = 0
        updated = 0
        deduped = 0
        tagged_links = 0

        seen_dedup_keys: set[str] = set()
        for candidate in candidates:
            dedup_key = build_dedup_key(candidate)
            if dedup_key in seen_dedup_keys:
                deduped += 1
                continue
            seen_dedup_keys.add(dedup_key)

            sentiment_label, sentiment_score = label_sentiment(candidate)
            tagged_assets = tag_assets(candidate, assets)
            importance = score_importance(
                candidate=candidate,
                sentiment_score=sentiment_score,
                relevance_scores=[tagged.relevance_score for tagged in tagged_assets],
            )
            metadata = {
                "provider_sentiment_score": candidate.provider_sentiment_score,
                "provider_sentiment_label": candidate.provider_sentiment_label,
                "provider_tickers": candidate.provider_tickers,
                "tagged_assets": [tagged.normalized_symbol for tagged in tagged_assets],
            }

            stored, created = self._repository.upsert_news_item(
                provider_id=provider.id,
                external_id=candidate.external_id,
                source_name=candidate.source_name,
                title=candidate.title,
                summary=candidate.summary,
                url=candidate.url,
                published_at=candidate.published_at,
                sentiment_label=sentiment_label,
                importance_score=importance,
                dedup_key=dedup_key,
                metadata=metadata,
            )
            if created:
                inserted += 1
            else:
                updated += 1

            for tagged_asset in tagged_assets:
                self._repository.upsert_news_asset_link(
                    news_item_id=stored.id,
                    asset_id=UUID(tagged_asset.asset_id),
                    relevance_score=tagged_asset.relevance_score,
                )
                tagged_links += 1

        duration_ms = int((perf_counter() - started) * 1000)
        return NewsIngestionSummary(
            provider_code=provider_code,
            fetched_count=len(candidates),
            inserted_count=inserted,
            updated_count=updated,
            deduplicated_count=deduped,
            tagged_links_count=tagged_links,
            duration_ms=duration_ms,
        )

    def list_feed(
        self,
        *,
        limit: int,
        hours: int,
        symbol: str | None,
        asset_class: str | None,
    ) -> list[FeedNewsRow]:
        normalized_symbol = None
        if symbol:
            typed_asset_class = cast(AssetClass | None, asset_class)
            try:
                normalized = normalize_symbol(symbol, asset_class=typed_asset_class)
            except SymbolNormalizationError as exc:
                raise NewsContextError(str(exc)) from exc
            normalized_symbol = normalized.normalized_symbol
        return self._repository.list_news_feed(
            limit=limit,
            normalized_symbol=normalized_symbol,
            hours=hours,
        )

    def provider_codes(self) -> list[str]:
        return self._adapter_registry.provider_codes()


def _normalize_symbol_filters(symbols: list[str] | None, asset_class: str | None) -> list[str]:
    if not symbols:
        return []
    typed_asset_class = cast(AssetClass | None, asset_class)
    output: list[str] = []
    for symbol in symbols:
        normalized = normalize_symbol(symbol, asset_class=typed_asset_class)
        output.append(normalized.base_currency)
    return sorted(set(output))


_news_service_instance: NewsContextService | None = None


def get_news_context_service() -> NewsContextService:
    global _news_service_instance
    if _news_service_instance is None:
        repository = NewsContextRepository(session_factory=SessionLocal)
        registry = build_news_registry(
            alpha_vantage_api_key=settings.alpha_vantage_api_key,
            cache_ttl_seconds=settings.news_cache_ttl_seconds,
            retry_attempts=settings.news_retry_attempts,
            retry_backoff_seconds=settings.news_retry_backoff_seconds,
        )
        _news_service_instance = NewsContextService(repository=repository, adapter_registry=registry)
    return _news_service_instance


def reset_news_context_service_for_tests() -> None:
    global _news_service_instance
    _news_service_instance = None
