from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.analysis.domain import SetupType

ConfidenceLabel = Literal["low", "medium", "high"]
TradeDirection = Literal["bullish", "bearish", "neutral"]


class TradeIdeaRequest(BaseModel):
    symbol: str = Field(description="Asset symbol, e.g. BTCUSDT or EUR/USD")
    timeframe: str = Field(default="1h")
    asset_class: Literal["crypto", "forex"] | None = None
    candle_limit: int = Field(default=300, ge=60, le=2000)
    news_limit: int = Field(default=20, ge=1, le=200)
    news_hours: int = Field(default=72, ge=1, le=720)


class ConfidenceOut(BaseModel):
    label: ConfidenceLabel
    score: float
    explanation: str


class InvalidationOut(BaseModel):
    level: float | None
    condition: str


class TradeIdeaResponse(BaseModel):
    symbol: str
    timeframe: str
    generated_at: datetime
    setup_direction: TradeDirection
    setup_type: SetupType | None
    supporting_factors: list[str]
    contradictory_factors: list[str]
    invalidation: InvalidationOut
    confidence: ConfidenceOut
    thesis_summary: str
    disclaimer: str
