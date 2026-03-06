from app.analysis.indicators import candles_to_frame, compute_indicators
from tests.analysis.utils import make_trending_candles


def test_compute_indicators_generates_required_columns() -> None:
    candles = make_trending_candles(count=280)
    frame = candles_to_frame(candles)
    output = compute_indicators(frame)

    latest = output.iloc[-1]
    required_columns = [
        "sma_20",
        "ema_20",
        "ema_50",
        "ema_200",
        "rsi_14",
        "macd_line",
        "macd_signal",
        "atr_14",
        "bb_upper",
        "bb_lower",
        "adx_14",
    ]
    for col in required_columns:
        assert col in output.columns
        assert latest[col] == latest[col]

    assert latest["ema_20"] > latest["ema_50"] > latest["ema_200"]
