from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.analysis.domain import SetupDirection, SetupType

ConfidenceLabel = Literal["low", "medium", "high"]
TradeDirection = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class Invalidation:
    level: float | None
    condition: str


@dataclass(frozen=True)
class Confidence:
    label: ConfidenceLabel
    score: float
    explanation: str


@dataclass(frozen=True)
class TradeThesis:
    symbol: str
    timeframe: str
    generated_at: datetime
    setup_direction: TradeDirection
    setup_type: SetupType | None
    supporting_factors: list[str]
    contradictory_factors: list[str]
    invalidation: Invalidation
    confidence: Confidence
    thesis_summary: str
    disclaimer: str
