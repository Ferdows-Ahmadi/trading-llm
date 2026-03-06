from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TrendRegimeLabel = Literal[
    "bull_trend",
    "bear_trend",
    "range_compression",
    "range",
    "transition",
    "insufficient_data",
]
SetupType = Literal["breakout", "pullback_continuation", "mean_reversion"]
SetupDirection = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class TrendRegime:
    label: TrendRegimeLabel
    confidence: float
    adx: float | None
    ema_gap_pct: float | None
    ema_slope_pct: float | None
    bb_width: float | None


@dataclass(frozen=True)
class PriceLevel:
    level: float
    touches: int
    distance_pct: float


@dataclass(frozen=True)
class SetupSignal:
    setup_type: SetupType
    direction: SetupDirection
    triggered: bool
    score: float
    reasons: list[str]
    trigger_price: float | None
    stop_hint: float | None
    target_hint: float | None


@dataclass(frozen=True)
class ScoreBreakdown:
    trend_score: float
    momentum_score: float
    volatility_score: float
    setup_score: float
    total_score: float


@dataclass(frozen=True)
class AnalysisResult:
    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    latest_close: float
    latest_indicators: dict[str, float | None]
    trend_regime: TrendRegime
    supports: list[PriceLevel]
    resistances: list[PriceLevel]
    setups: list[SetupSignal]
    score: ScoreBreakdown
