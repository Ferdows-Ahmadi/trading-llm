from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NewsIngestionRequest(BaseModel):
    provider_code: str = Field(default="alpha_vantage")
    limit: int = Field(default=50, ge=1, le=200)
    symbols: list[str] | None = None
    asset_class: Literal["crypto", "forex"] | None = None


class NewsIngestionResponse(BaseModel):
    provider_code: str
    fetched_count: int
    inserted_count: int
    updated_count: int
    deduplicated_count: int
    tagged_links_count: int
    duration_ms: int


class ContradictionSignalOut(BaseModel):
    asset_symbol: str
    price_change_pct_24h: float
    is_contradiction: bool


class NewsFeedItemOut(BaseModel):
    id: str
    title: str
    summary: str
    url: str
    source_name: str
    published_at: datetime
    sentiment_label: str | None
    importance_score: float | None
    asset_symbols: list[str]
    contradiction_signals: list[ContradictionSignalOut]


class NewsFeedResponse(BaseModel):
    items: list[NewsFeedItemOut]
