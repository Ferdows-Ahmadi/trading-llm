from app.analysis.indicators import candles_to_frame, compute_indicators
from app.analysis.regime import classify_trend_regime
from tests.analysis.utils import make_trending_candles


def test_regime_classifier_detects_bull_trend() -> None:
    candles = make_trending_candles(count=320, drift=0.33)
    indicators = compute_indicators(candles_to_frame(candles))

    regime = classify_trend_regime(indicators)
    assert regime.label == "bull_trend"
    assert regime.confidence >= 0.55
