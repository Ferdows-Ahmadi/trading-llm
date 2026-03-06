from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.analysis.domain import AnalysisResult, PriceLevel, ScoreBreakdown, SetupSignal, TrendRegime
from app.analysis.service import get_analysis_service
from app.main import app


class _FakeAnalysisService:
    def analyze_asset(self, **kwargs) -> AnalysisResult:  # type: ignore[no-untyped-def]
        _ = kwargs
        return AnalysisResult(
            symbol="BTCUSDT",
            timeframe="1h",
            analyzed_at=datetime(2026, 1, 1, tzinfo=UTC),
            candle_count=300,
            latest_close=105.5,
            latest_indicators={
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
                "adx_14": 29.4,
            },
            trend_regime=TrendRegime(
                label="bull_trend",
                confidence=0.74,
                adx=29.4,
                ema_gap_pct=4.46,
                ema_slope_pct=0.31,
                bb_width=0.075,
            ),
            supports=[PriceLevel(level=101.2, touches=3, distance_pct=-4.06)],
            resistances=[PriceLevel(level=106.8, touches=4, distance_pct=1.23)],
            setups=[
                SetupSignal(
                    setup_type="pullback_continuation",
                    direction="bullish",
                    triggered=True,
                    score=78.5,
                    reasons=["Bull trend regime confirmed.", "Price bounced from EMA20 pullback."],
                    trigger_price=105.5,
                    stop_hint=103.9,
                    target_hint=109.8,
                )
            ],
            score=ScoreBreakdown(
                trend_score=79.2,
                momentum_score=68.1,
                volatility_score=61.4,
                setup_score=78.5,
                total_score=72.99,
            ),
        )


def test_analysis_endpoint_returns_payload() -> None:
    app.dependency_overrides[get_analysis_service] = lambda: _FakeAnalysisService()
    client = TestClient(app)
    response = client.post(
        "/api/v1/analysis/run",
        json={"symbol": "BTCUSDT", "timeframe": "1h", "limit": 300, "asset_class": "crypto"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["trend_regime"]["label"] == "bull_trend"
    assert body["score"]["total_score"] == 72.99
