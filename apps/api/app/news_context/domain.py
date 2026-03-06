from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NewsCandidate:
    external_id: str | None
    source_name: str
    title: str
    summary: str
    url: str
    published_at: datetime
    provider_sentiment_score: float | None = None
    provider_sentiment_label: str | None = None
    provider_importance: float | None = None
    provider_tickers: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaggedAsset:
    asset_id: str
    normalized_symbol: str
    relevance_score: float


@dataclass(frozen=True)
class ProcessedNewsItem:
    candidate: NewsCandidate
    dedup_key: str
    sentiment_label: str
    importance_score: float
    tagged_assets: list[TaggedAsset]
