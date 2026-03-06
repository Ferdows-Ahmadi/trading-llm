from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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


class TrendRegimeOut(BaseModel):
    label: TrendRegimeLabel
    confidence: float
    adx: float | None
    ema_gap_pct: float | None
    ema_slope_pct: float | None
    bb_width: float | None


class PriceLevelOut(BaseModel):
    level: float
    touches: int
    distance_pct: float


class SetupSignalOut(BaseModel):
    setup_type: SetupType
    direction: SetupDirection
    triggered: bool
    score: float
    reasons: list[str]
    trigger_price: float | None
    stop_hint: float | None
    target_hint: float | None


class ScoreBreakdownOut(BaseModel):
    trend_score: float
    momentum_score: float
    volatility_score: float
    setup_score: float
    total_score: float


class AnalysisResponse(BaseModel):
    symbol: str
    timeframe: str
    analyzed_at: datetime
    candle_count: int
    latest_close: float
    latest_indicators: dict[str, float | None]
    trend_regime: TrendRegimeOut
    supports: list[PriceLevelOut]
    resistances: list[PriceLevelOut]
    setups: list[SetupSignalOut]
    score: ScoreBreakdownOut


class AnalysisRunRequest(BaseModel):
    symbol: str = Field(description="Asset symbol, e.g. BTCUSDT or EUR/USD")
    timeframe: str = Field(default="1h", description="Candle timeframe, e.g. 15m, 1h, 4h, 1d")
    limit: int = Field(default=300, ge=60, le=2000)
    asset_class: Literal["crypto", "forex"] | None = None
