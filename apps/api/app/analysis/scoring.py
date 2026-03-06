from __future__ import annotations

import pandas as pd

from app.analysis.domain import ScoreBreakdown, SetupSignal, TrendRegime


def score_asset(
    indicator_frame: pd.DataFrame,
    *,
    regime: TrendRegime,
    setups: list[SetupSignal],
) -> ScoreBreakdown:
    if indicator_frame.empty:
        return ScoreBreakdown(
            trend_score=0.0,
            momentum_score=0.0,
            volatility_score=0.0,
            setup_score=0.0,
            total_score=0.0,
        )

    latest = indicator_frame.iloc[-1]
    trend_score = _trend_score(latest=latest, regime=regime)
    momentum_score = _momentum_score(latest=latest)
    volatility_score = _volatility_score(latest=latest)
    setup_score = max((signal.score for signal in setups), default=35.0)

    total = (0.35 * trend_score) + (0.25 * momentum_score) + (0.15 * volatility_score) + (
        0.25 * setup_score
    )
    return ScoreBreakdown(
        trend_score=round(_clamp(trend_score), 2),
        momentum_score=round(_clamp(momentum_score), 2),
        volatility_score=round(_clamp(volatility_score), 2),
        setup_score=round(_clamp(setup_score), 2),
        total_score=round(_clamp(total), 2),
    )


def _trend_score(*, latest: pd.Series, regime: TrendRegime) -> float:
    ema50 = _f(latest, "ema_50")
    ema200 = _f(latest, "ema_200")
    adx = _f(latest, "adx_14")

    score = 50.0
    if ema50 > ema200:
        score += 10.0
    elif ema50 < ema200:
        score -= 10.0

    score += min(adx, 40.0) * 0.5

    if regime.label in {"bull_trend", "bear_trend"}:
        score += 10.0
    elif regime.label in {"range", "range_compression"}:
        score -= 5.0
    return score


def _momentum_score(*, latest: pd.Series) -> float:
    rsi = _f(latest, "rsi_14")
    macd_hist = _f(latest, "macd_hist")

    score = 50.0
    if 45.0 <= rsi <= 60.0:
        score += 12.0
    elif rsi < 30.0 or rsi > 70.0:
        score -= 8.0

    if macd_hist > 0:
        score += min(macd_hist * 300.0, 15.0)
    else:
        score -= min(abs(macd_hist) * 300.0, 15.0)
    return score


def _volatility_score(*, latest: pd.Series) -> float:
    atr_pct = _f(latest, "atr_pct")
    bb_width = _f(latest, "bb_width")

    score = 50.0
    if 0.003 <= atr_pct <= 0.03:
        score += 15.0
    elif atr_pct > 0.05:
        score -= 15.0
    else:
        score -= 5.0

    if 0.02 <= bb_width <= 0.12:
        score += 10.0
    elif bb_width > 0.2:
        score -= 10.0
    return score


def _f(series: pd.Series, key: str) -> float:
    value = series.get(key)
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
