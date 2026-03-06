from app.analysis.domain import SetupSignal, TrendRegime
from app.analysis.indicators import candles_to_frame, compute_indicators
from app.analysis.scoring import score_asset
from tests.analysis.utils import make_trending_candles


def test_scoring_output_is_bounded_and_weighted() -> None:
    frame = compute_indicators(candles_to_frame(make_trending_candles(count=280)))
    regime = TrendRegime(
        label="bull_trend",
        confidence=0.75,
        adx=30.0,
        ema_gap_pct=1.9,
        ema_slope_pct=0.4,
        bb_width=0.06,
    )
    setups = [
        SetupSignal(
            setup_type="breakout",
            direction="bullish",
            triggered=True,
            score=82.0,
            reasons=["test"],
            trigger_price=101.0,
            stop_hint=98.0,
            target_hint=107.0,
        )
    ]

    output = score_asset(frame, regime=regime, setups=setups)
    assert 0.0 <= output.trend_score <= 100.0
    assert 0.0 <= output.total_score <= 100.0
    assert output.setup_score == 82.0
