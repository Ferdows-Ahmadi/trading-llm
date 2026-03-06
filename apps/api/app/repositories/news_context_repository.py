from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.market_data import Asset, Candle, Provider
from app.models.news_context import NewsAssetLink, NewsItem


@dataclass(frozen=True)
class ProviderRef:
    id: uuid.UUID
    code: str
    rate_limit_per_minute: int | None


@dataclass(frozen=True)
class AssetRef:
    id: uuid.UUID
    normalized_symbol: str
    base_currency: str
    quote_currency: str
    display_symbol: str
    asset_class: str


@dataclass(frozen=True)
class StoredNewsItem:
    id: uuid.UUID
    title: str
    summary: str
    url: str
    source_name: str
    published_at: datetime
    sentiment_label: str | None
    importance_score: float | None
    dedup_key: str | None
    metadata: dict[str, object]


@dataclass(frozen=True)
class FeedNewsRow:
    id: str
    title: str
    summary: str
    url: str
    source_name: str
    published_at: datetime
    sentiment_label: str | None
    importance_score: float | None
    asset_symbols: list[str]
    contradiction_signals: list[dict[str, object]]


class NewsContextRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get_or_create_provider(self, provider_code: str) -> ProviderRef:
        with self._session_factory() as session:
            provider = session.scalar(select(Provider).where(Provider.code == provider_code))
            if provider is None:
                provider = Provider(
                    code=provider_code,
                    name=_provider_display_name(provider_code),
                    category="news_context",
                    is_enabled=True,
                )
                session.add(provider)
                session.commit()
                session.refresh(provider)
            return ProviderRef(
                id=provider.id,
                code=provider.code,
                rate_limit_per_minute=provider.rate_limit_per_minute,
            )

    def list_assets(self) -> list[AssetRef]:
        with self._session_factory() as session:
            rows = session.scalars(select(Asset).where(Asset.is_active.is_(True))).all()
            return [
                AssetRef(
                    id=row.id,
                    normalized_symbol=row.normalized_symbol,
                    base_currency=row.base_currency,
                    quote_currency=row.quote_currency,
                    display_symbol=row.symbol,
                    asset_class=row.asset_class,
                )
                for row in rows
            ]

    def upsert_news_item(
        self,
        *,
        provider_id: uuid.UUID,
        external_id: str | None,
        source_name: str,
        title: str,
        summary: str,
        url: str,
        published_at: datetime,
        sentiment_label: str,
        importance_score: float,
        dedup_key: str,
        metadata: dict[str, object],
    ) -> tuple[StoredNewsItem, bool]:
        with self._session_factory() as session:
            existing = session.scalar(
                select(NewsItem).where(
                    or_(
                        NewsItem.url == url,
                        and_(NewsItem.dedup_key == dedup_key, NewsItem.source_name == source_name),
                    )
                )
            )
            created = False
            if existing is None:
                item = NewsItem(
                    provider_id=provider_id,
                    external_id=external_id,
                    source_name=source_name,
                    title=title,
                    summary=summary,
                    url=url,
                    published_at=published_at,
                    sentiment_label=sentiment_label,
                    importance_score=Decimal(str(round(importance_score, 2))),
                    dedup_key=dedup_key,
                    metadata_json=metadata,
                )
                session.add(item)
                session.commit()
                session.refresh(item)
                created = True
            else:
                existing.provider_id = provider_id
                existing.external_id = external_id
                existing.title = title
                existing.summary = summary
                existing.url = url
                existing.published_at = published_at
                existing.sentiment_label = sentiment_label
                existing.importance_score = Decimal(str(round(importance_score, 2)))
                existing.dedup_key = dedup_key
                existing.metadata_json = metadata
                session.commit()
                session.refresh(existing)
                item = existing

            return (
                StoredNewsItem(
                    id=item.id,
                    title=item.title,
                    summary=item.summary or "",
                    url=item.url or "",
                    source_name=item.source_name,
                    published_at=item.published_at,
                    sentiment_label=item.sentiment_label,
                    importance_score=float(item.importance_score) if item.importance_score is not None else None,
                    dedup_key=item.dedup_key,
                    metadata=item.metadata_json,
                ),
                created,
            )

    def upsert_news_asset_link(
        self,
        *,
        news_item_id: uuid.UUID,
        asset_id: uuid.UUID,
        relevance_score: float,
    ) -> None:
        with self._session_factory() as session:
            existing = session.scalar(
                select(NewsAssetLink).where(
                    NewsAssetLink.news_item_id == news_item_id,
                    NewsAssetLink.asset_id == asset_id,
                )
            )
            relevance_decimal = Decimal(str(round(relevance_score, 2)))
            if existing is None:
                session.add(
                    NewsAssetLink(
                        news_item_id=news_item_id,
                        asset_id=asset_id,
                        relevance_score=relevance_decimal,
                    )
                )
            else:
                existing.relevance_score = relevance_decimal
            session.commit()

    def list_news_feed(
        self,
        *,
        limit: int,
        normalized_symbol: str | None,
        hours: int,
    ) -> list[FeedNewsRow]:
        with self._session_factory() as session:
            since = datetime.now(tz=UTC) - timedelta(hours=hours)

            item_query: Select[tuple[NewsItem]] = select(NewsItem).where(NewsItem.published_at >= since)
            if normalized_symbol:
                item_query = item_query.join(
                    NewsAssetLink,
                    NewsAssetLink.news_item_id == NewsItem.id,
                ).join(Asset, Asset.id == NewsAssetLink.asset_id).where(
                    Asset.normalized_symbol == normalized_symbol
                )
            item_query = item_query.order_by(NewsItem.published_at.desc()).limit(limit)
            items = session.scalars(item_query).all()

            if not items:
                return []

            item_ids = [item.id for item in items]
            link_rows = session.execute(
                select(NewsAssetLink.news_item_id, Asset.id, Asset.normalized_symbol)
                .join(Asset, Asset.id == NewsAssetLink.asset_id)
                .where(NewsAssetLink.news_item_id.in_(item_ids))
            ).all()
            links_by_item: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {}
            for news_item_id, asset_id, symbol in link_rows:
                links_by_item.setdefault(news_item_id, []).append((asset_id, symbol))

            contradictions_by_item = self._build_contradiction_signals(
                session=session,
                items=items,
                links_by_item=links_by_item,
            )

            output: list[FeedNewsRow] = []
            for item in items:
                linked_assets = links_by_item.get(item.id, [])
                output.append(
                    FeedNewsRow(
                        id=str(item.id),
                        title=item.title,
                        summary=item.summary or "",
                        url=item.url or "",
                        source_name=item.source_name,
                        published_at=item.published_at,
                        sentiment_label=item.sentiment_label,
                        importance_score=(
                            float(item.importance_score) if item.importance_score is not None else None
                        ),
                        asset_symbols=[symbol for _, symbol in linked_assets],
                        contradiction_signals=contradictions_by_item.get(item.id, []),
                    )
                )
            return output

    def _build_contradiction_signals(
        self,
        *,
        session: Session,
        items: list[NewsItem],
        links_by_item: dict[uuid.UUID, list[tuple[uuid.UUID, str]]],
    ) -> dict[uuid.UUID, list[dict[str, object]]]:
        if not items:
            return {}

        asset_ids: set[uuid.UUID] = set()
        for linked in links_by_item.values():
            for asset_id, _ in linked:
                asset_ids.add(asset_id)
        if not asset_ids:
            return {}

        recent_candles = session.execute(
            select(Candle.asset_id, Candle.open_time, Candle.close)
            .where(Candle.asset_id.in_(list(asset_ids)), Candle.timeframe == "1h")
            .order_by(Candle.asset_id.asc(), Candle.open_time.desc())
        ).all()

        by_asset: dict[uuid.UUID, list[tuple[datetime, float]]] = {}
        for asset_id, open_time, close in recent_candles:
            entries = by_asset.setdefault(asset_id, [])
            if len(entries) < 30:
                entries.append((open_time, float(close)))

        change_pct_by_asset: dict[uuid.UUID, float] = {}
        for asset_id, values in by_asset.items():
            if len(values) < 2:
                continue
            sorted_vals = sorted(values, key=lambda value: value[0])
            first = sorted_vals[0][1]
            last = sorted_vals[-1][1]
            if first != 0:
                change_pct_by_asset[asset_id] = ((last - first) / first) * 100

        output: dict[uuid.UUID, list[dict[str, object]]] = {}
        for item in items:
            sentiment = (item.sentiment_label or "neutral").lower()
            rows: list[dict[str, object]] = []
            for asset_id, symbol in links_by_item.get(item.id, []):
                change_pct = change_pct_by_asset.get(asset_id)
                if change_pct is None:
                    continue
                is_contradiction = _sentiment_price_contradiction(sentiment, change_pct)
                rows.append(
                    {
                        "asset_symbol": symbol,
                        "price_change_pct_24h": round(change_pct, 4),
                        "is_contradiction": is_contradiction,
                    }
                )
            output[item.id] = rows
        return output


def _provider_display_name(provider_code: str) -> str:
    display_names = {
        "alpha_vantage": "Alpha Vantage",
    }
    return display_names.get(provider_code, provider_code.upper())


def _sentiment_price_contradiction(sentiment: str, price_change_pct: float) -> bool:
    if sentiment == "positive" and price_change_pct <= -1.0:
        return True
    if sentiment == "negative" and price_change_pct >= 1.0:
        return True
    return False
