from __future__ import annotations

import pandas as pd

from app.analysis.domain import TrendRegime


def classify_trend_regime(indicator_frame: pd.DataFrame) -> TrendRegime:
    if indicator_frame.empty or len(indicator_frame) < 30:
        return TrendRegime(
            label="insufficient_data",
            confidence=0.0,
            adx=None,
            ema_gap_pct=None,
            ema_slope_pct=None,
            bb_width=None,
        )

    latest = indicator_frame.iloc[-1]
    adx = _safe_float(latest.get("adx_14"))
    ema_50 = _safe_float(latest.get("ema_50"))
    ema_200 = _safe_float(latest.get("ema_200"))
    bb_width = _safe_float(latest.get("bb_width"))

    if ema_50 is None or ema_200 is None:
        return TrendRegime(
            label="insufficient_data",
            confidence=0.0,
            adx=adx,
            ema_gap_pct=None,
            ema_slope_pct=None,
            bb_width=bb_width,
        )

    ema_gap_pct = ((ema_50 - ema_200) / ema_200) * 100 if ema_200 != 0 else 0.0
    ema_slope_pct = _ema_slope_pct(indicator_frame, periods=5)

    if adx is not None and adx >= 25 and ema_gap_pct > 0 and ema_slope_pct > 0:
        confidence = _bounded(0.55 + min(adx / 100, 0.3) + min(abs(ema_gap_pct) / 10, 0.15))
        return TrendRegime(
            label="bull_trend",
            confidence=confidence,
            adx=adx,
            ema_gap_pct=ema_gap_pct,
            ema_slope_pct=ema_slope_pct,
            bb_width=bb_width,
        )

    if adx is not None and adx >= 25 and ema_gap_pct < 0 and ema_slope_pct < 0:
        confidence = _bounded(0.55 + min(adx / 100, 0.3) + min(abs(ema_gap_pct) / 10, 0.15))
        return TrendRegime(
            label="bear_trend",
            confidence=confidence,
            adx=adx,
            ema_gap_pct=ema_gap_pct,
            ema_slope_pct=ema_slope_pct,
            bb_width=bb_width,
        )

    if adx is not None and adx < 18 and (bb_width is not None and bb_width < 0.05):
        return TrendRegime(
            label="range_compression",
            confidence=0.65,
            adx=adx,
            ema_gap_pct=ema_gap_pct,
            ema_slope_pct=ema_slope_pct,
            bb_width=bb_width,
        )

    if adx is not None and adx < 25:
        return TrendRegime(
            label="range",
            confidence=0.58,
            adx=adx,
            ema_gap_pct=ema_gap_pct,
            ema_slope_pct=ema_slope_pct,
            bb_width=bb_width,
        )

    return TrendRegime(
        label="transition",
        confidence=0.5,
        adx=adx,
        ema_gap_pct=ema_gap_pct,
        ema_slope_pct=ema_slope_pct,
        bb_width=bb_width,
    )


def _ema_slope_pct(frame: pd.DataFrame, periods: int) -> float:
    if len(frame) <= periods:
        return 0.0
    latest = _safe_float(frame.iloc[-1].get("ema_50"))
    previous = _safe_float(frame.iloc[-(periods + 1)].get("ema_50"))
    if latest is None or previous is None or previous == 0:
        return 0.0
    return ((latest - previous) / previous) * 100


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        casted = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(casted):
        return None
    return casted


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))
