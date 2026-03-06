# Deterministic Analysis Engine

## Implemented capabilities
- Indicators:
  - EMA (`20`, `50`, `200`)
  - SMA (`20`)
  - RSI (`14`)
  - MACD (`12/26/9`)
  - ATR (`14`)
  - Bollinger Bands (`20`, `2 std`)
  - ADX (`14`)
- Trend regime classification:
  - `bull_trend`, `bear_trend`, `range_compression`, `range`, `transition`
- Support/resistance detection:
  - swing high/low pivots
  - clustered levels with touch counts
- Setup detectors:
  - breakout / breakdown
  - pullback continuation
  - mean reversion
- Scoring outputs:
  - trend, momentum, volatility, setup, and weighted total scores

## Deterministic design
- No LLM dependency in this phase.
- Analysis is based only on stored OHLCV candles and hard-coded rule thresholds.
- Every setup output includes explicit reasons and suggested trigger/stop/target hints.

## API
- `POST /api/v1/analysis/run`
  - Input: symbol, timeframe, candle limit, optional asset_class
  - Output: indicators snapshot, regime, support/resistance levels, triggered setups, score breakdown

## Sample output
```json
{
  "symbol": "BTCUSDT",
  "timeframe": "1h",
  "analyzed_at": "2026-01-01T00:00:00+00:00",
  "candle_count": 300,
  "latest_close": 105.5,
  "latest_indicators": {
    "sma_20": 102.1,
    "ema_20": 102.8,
    "ema_50": 100.6,
    "ema_200": 96.3,
    "rsi_14": 58.2,
    "macd_line": 1.3,
    "macd_signal": 0.9,
    "macd_hist": 0.4,
    "atr_14": 1.1,
    "bb_upper": 106.0,
    "bb_middle": 102.1,
    "bb_lower": 98.2,
    "adx_14": 29.4
  },
  "trend_regime": {
    "label": "bull_trend",
    "confidence": 0.74,
    "adx": 29.4,
    "ema_gap_pct": 4.46,
    "ema_slope_pct": 0.31,
    "bb_width": 0.075
  },
  "supports": [
    { "level": 101.2, "touches": 3, "distance_pct": -4.06 }
  ],
  "resistances": [
    { "level": 106.8, "touches": 4, "distance_pct": 1.23 }
  ],
  "setups": [
    {
      "setup_type": "pullback_continuation",
      "direction": "bullish",
      "triggered": true,
      "score": 78.5,
      "reasons": [
        "Bull trend regime confirmed.",
        "Price pulled back toward EMA20 and bounced.",
        "Pullback stayed within ATR-guided bounds."
      ],
      "trigger_price": 105.5,
      "stop_hint": 103.9,
      "target_hint": 109.8
    }
  ],
  "score": {
    "trend_score": 79.2,
    "momentum_score": 68.1,
    "volatility_score": 61.4,
    "setup_score": 78.5,
    "total_score": 72.99
  }
}
```

Also available as a reusable file: `docs/samples/analysis-run-sample.json`.
