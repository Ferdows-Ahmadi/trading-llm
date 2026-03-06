from __future__ import annotations

import pandas as pd

from app.analysis.domain import PriceLevel, TrendRegime
from app.analysis.setups import detect_setups


def test_breakout_setup_detection() -> None:
    frame = pd.DataFrame(
        [
            {
                "close": 100.0,
                "low": 99.0,
                "high": 101.0,
                "volume": 1000.0,
                "volume_sma_20": 900.0,
                "adx_14": 28.0,
                "ema_20": 99.8,
                "atr_14": 1.1,
                "bb_upper": 102.0,
                "bb_lower": 98.0,
                "bb_middle": 100.0,
                "rsi_14": 59.0,
            },
            {
                "close": 103.2,
                "low": 101.0,
                "high": 103.7,
                "volume": 1400.0,
                "volume_sma_20": 900.0,
                "adx_14": 31.0,
                "ema_20": 100.2,
                "atr_14": 1.2,
                "bb_upper": 103.0,
                "bb_lower": 98.2,
                "bb_middle": 100.6,
                "rsi_14": 62.0,
            },
        ]
    )
    regime = TrendRegime(
        label="bull_trend",
        confidence=0.72,
        adx=31.0,
        ema_gap_pct=1.8,
        ema_slope_pct=0.4,
        bb_width=0.05,
    )
    supports = [PriceLevel(level=98.5, touches=3, distance_pct=-4.3)]
    resistances = [PriceLevel(level=102.5, touches=3, distance_pct=1.2)]

    setups = detect_setups(frame, regime=regime, supports=supports, resistances=resistances)
    breakout = next(setup for setup in setups if setup.setup_type == "breakout")
    assert breakout.triggered
    assert breakout.direction == "bullish"
    assert breakout.score >= 62


def test_mean_reversion_setup_detection() -> None:
    frame = pd.DataFrame(
        [
            {
                "close": 100.0,
                "low": 99.0,
                "high": 101.0,
                "volume": 1000.0,
                "volume_sma_20": 1000.0,
                "adx_14": 16.0,
                "ema_20": 100.0,
                "atr_14": 1.2,
                "bb_upper": 102.0,
                "bb_lower": 98.5,
                "bb_middle": 100.2,
                "rsi_14": 48.0,
            },
            {
                "close": 97.9,
                "low": 97.5,
                "high": 99.0,
                "volume": 900.0,
                "volume_sma_20": 980.0,
                "adx_14": 17.0,
                "ema_20": 99.8,
                "atr_14": 1.3,
                "bb_upper": 101.5,
                "bb_lower": 98.3,
                "bb_middle": 100.0,
                "rsi_14": 31.0,
            },
        ]
    )
    regime = TrendRegime(
        label="range",
        confidence=0.6,
        adx=17.0,
        ema_gap_pct=0.1,
        ema_slope_pct=0.0,
        bb_width=0.03,
    )

    setups = detect_setups(frame, regime=regime, supports=[], resistances=[])
    mean_reversion = next(setup for setup in setups if setup.setup_type == "mean_reversion")
    assert mean_reversion.direction == "bullish"
    assert mean_reversion.triggered
