from __future__ import annotations

import pandas as pd

from app.analysis.domain import PriceLevel, SetupSignal, TrendRegime


def detect_setups(
    indicator_frame: pd.DataFrame,
    *,
    regime: TrendRegime,
    supports: list[PriceLevel],
    resistances: list[PriceLevel],
) -> list[SetupSignal]:
    if indicator_frame.empty or len(indicator_frame) < 25:
        return []

    latest = indicator_frame.iloc[-1]
    previous = indicator_frame.iloc[-2]
    setups = [
        _detect_breakout(latest=latest, previous=previous, supports=supports, resistances=resistances),
        _detect_pullback(latest=latest, previous=previous, regime=regime),
        _detect_mean_reversion(latest=latest, regime=regime),
    ]
    return [setup for setup in setups if setup is not None]


def _detect_breakout(
    *,
    latest: pd.Series,
    previous: pd.Series,
    supports: list[PriceLevel],
    resistances: list[PriceLevel],
) -> SetupSignal | None:
    close_now = _f(latest, "close")
    close_prev = _f(previous, "close")
    volume_now = _f(latest, "volume")
    volume_avg = _f(latest, "volume_sma_20")
    adx = _f(latest, "adx_14")

    nearest_resistance = resistances[0].level if resistances else None
    nearest_support = supports[0].level if supports else None

    if (
        nearest_resistance is not None
        and close_now > nearest_resistance * 1.0025
        and close_prev <= nearest_resistance
    ):
        volume_boost = volume_now > volume_avg * 1.2 if volume_avg > 0 else False
        score = 62.0 + min(max(adx - 20.0, 0.0), 20.0) + (8.0 if volume_boost else 0.0)
        return SetupSignal(
            setup_type="breakout",
            direction="bullish",
            triggered=True,
            score=min(score, 99.0),
            reasons=[
                "Price closed above nearest resistance with threshold buffer.",
                "Breakout confirmation based on previous close below/at resistance.",
                "Volume expansion detected." if volume_boost else "No strong volume expansion signal.",
            ],
            trigger_price=close_now,
            stop_hint=nearest_resistance,
            target_hint=close_now + (close_now - nearest_resistance) * 1.5,
        )

    if nearest_support is not None and close_now < nearest_support * 0.9975 and close_prev >= nearest_support:
        volume_boost = volume_now > volume_avg * 1.2 if volume_avg > 0 else False
        score = 62.0 + min(max(adx - 20.0, 0.0), 20.0) + (8.0 if volume_boost else 0.0)
        return SetupSignal(
            setup_type="breakout",
            direction="bearish",
            triggered=True,
            score=min(score, 99.0),
            reasons=[
                "Price closed below nearest support with threshold buffer.",
                "Breakdown confirmation based on previous close above/at support.",
                "Volume expansion detected." if volume_boost else "No strong volume expansion signal.",
            ],
            trigger_price=close_now,
            stop_hint=nearest_support,
            target_hint=close_now - (nearest_support - close_now) * 1.5,
        )

    return None


def _detect_pullback(*, latest: pd.Series, previous: pd.Series, regime: TrendRegime) -> SetupSignal | None:
    close_now = _f(latest, "close")
    close_prev = _f(previous, "close")
    ema20_now = _f(latest, "ema_20")
    ema20_prev = _f(previous, "ema_20")
    low_prev = _f(previous, "low")
    high_prev = _f(previous, "high")
    atr_now = max(_f(latest, "atr_14"), 1e-9)

    if regime.label == "bull_trend":
        touched = low_prev <= ema20_prev + (0.2 * atr_now)
        near_ema = abs(close_now - ema20_now) <= 0.5 * atr_now
        bounce = close_now > close_prev
        if touched and near_ema and bounce:
            score = min(58.0 + (regime.confidence * 25.0), 96.0)
            return SetupSignal(
                setup_type="pullback_continuation",
                direction="bullish",
                triggered=True,
                score=score,
                reasons=[
                    "Bull trend regime confirmed.",
                    "Price pulled back toward EMA20 and bounced.",
                    "Pullback stayed within ATR-guided bounds.",
                ],
                trigger_price=close_now,
                stop_hint=low_prev - (0.5 * atr_now),
                target_hint=close_now + (close_now - low_prev) * 1.8,
            )

    if regime.label == "bear_trend":
        touched = high_prev >= ema20_prev - (0.2 * atr_now)
        near_ema = abs(close_now - ema20_now) <= 0.5 * atr_now
        rejection = close_now < close_prev
        if touched and near_ema and rejection:
            score = min(58.0 + (regime.confidence * 25.0), 96.0)
            return SetupSignal(
                setup_type="pullback_continuation",
                direction="bearish",
                triggered=True,
                score=score,
                reasons=[
                    "Bear trend regime confirmed.",
                    "Price pulled back toward EMA20 and rejected.",
                    "Pullback stayed within ATR-guided bounds.",
                ],
                trigger_price=close_now,
                stop_hint=high_prev + (0.5 * atr_now),
                target_hint=close_now - (high_prev - close_now) * 1.8,
            )

    return None


def _detect_mean_reversion(*, latest: pd.Series, regime: TrendRegime) -> SetupSignal | None:
    close_now = _f(latest, "close")
    upper = _f(latest, "bb_upper")
    lower = _f(latest, "bb_lower")
    middle = _f(latest, "bb_middle")
    rsi = _f(latest, "rsi_14")
    adx = _f(latest, "adx_14")

    range_friendly = regime.label in {"range", "range_compression", "transition"} or adx < 25.0
    if not range_friendly:
        return None

    if close_now < lower and rsi <= 35:
        score = min(55.0 + ((35.0 - rsi) * 0.7), 92.0)
        return SetupSignal(
            setup_type="mean_reversion",
            direction="bullish",
            triggered=True,
            score=score,
            reasons=[
                "Price stretched below lower Bollinger Band.",
                "RSI indicates oversold conditions.",
                "Regime is non-trending or transitional.",
            ],
            trigger_price=close_now,
            stop_hint=close_now * 0.99,
            target_hint=middle,
        )

    if close_now > upper and rsi >= 65:
        score = min(55.0 + ((rsi - 65.0) * 0.7), 92.0)
        return SetupSignal(
            setup_type="mean_reversion",
            direction="bearish",
            triggered=True,
            score=score,
            reasons=[
                "Price stretched above upper Bollinger Band.",
                "RSI indicates overbought conditions.",
                "Regime is non-trending or transitional.",
            ],
            trigger_price=close_now,
            stop_hint=close_now * 1.01,
            target_hint=middle,
        )

    return None


def _f(series: pd.Series, key: str) -> float:
    value = series.get(key)
    if value is None or pd.isna(value):
        return 0.0
    return float(value)
