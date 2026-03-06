from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.repositories.market_data_repository import CandleRecord


def candles_to_frame(candles: Sequence[CandleRecord]) -> pd.DataFrame:
    rows = [
        {
            "open_time": candle.open_time,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume if candle.volume is not None else 0.0,
        }
        for candle in candles
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame.sort_values("open_time", inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def compute_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    df = frame.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    df["sma_20"] = close.rolling(window=20, min_periods=20).mean()
    df["ema_20"] = close.ewm(span=20, adjust=False).mean()
    df["ema_50"] = close.ewm(span=50, adjust=False).mean()
    df["ema_200"] = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    df["rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df["macd_line"] = ema_12 - ema_26
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]

    previous_close = close.shift(1)
    tr_components = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    )
    tr = tr_components.max(axis=1)
    df["atr_14"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["atr_pct"] = df["atr_14"] / close.replace(0.0, np.nan)

    rolling_std = close.rolling(window=20, min_periods=20).std(ddof=0)
    df["bb_middle"] = df["sma_20"]
    df["bb_upper"] = df["bb_middle"] + (2.0 * rolling_std)
    df["bb_lower"] = df["bb_middle"] - (2.0 * rolling_std)
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / close.replace(0.0, np.nan)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=df.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=df.index,
    )
    atr_for_adx = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr_for_adx
    minus_di = 100.0 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / atr_for_adx
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)) * 100.0
    df["adx_14"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    df["volume_sma_20"] = df["volume"].rolling(window=20, min_periods=20).mean()
    return df
