from __future__ import annotations

from datetime import UTC, datetime

from app.analysis.domain import AnalysisResult, PriceLevel, ScoreBreakdown, SetupSignal, TrendRegime
from app.repositories.news_context_repository import FeedNewsRow
from app.trade_ideas.service import TradeIdeaService


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
                "ema_20": 104.9,
                "ema_50": 102.0,
                "ema_200": 97.0,
                "rsi_14": 61.2,
                "macd_hist": 0.45,
            },
            trend_regime=TrendRegime(
                label="bull_trend",
                confidence=0.74,
                adx=29.3,
                ema_gap_pct=3.2,
                ema_slope_pct=0.5,
                bb_width=0.07,
            ),
            supports=[PriceLevel(level=103.2, touches=4, distance_pct=-2.1)],
            resistances=[PriceLevel(level=108.7, touches=3, distance_pct=3.0)],
            setups=[
                SetupSignal(
                    setup_type="pullback_continuation",
                    direction="bullish",
                    triggered=True,
                    score=78.5,
                    reasons=["Bull trend regime confirmed.", "Price pulled back toward EMA20 and bounced."],
                    trigger_price=105.5,
                    stop_hint=103.9,
                    target_hint=110.3,
                )
            ],
            score=ScoreBreakdown(
                trend_score=79.0,
                momentum_score=68.0,
                volatility_score=60.0,
                setup_score=78.5,
                total_score=72.6,
            ),
        )


class _FakeNewsService:
    def list_feed(self, **kwargs) -> list[FeedNewsRow]:  # type: ignore[no-untyped-def]
        _ = kwargs
        return [
            FeedNewsRow(
                id="n1",
                title="BTC rallies on improved sentiment",
                summary="Summary",
                url="https://example.com/1",
                source_name="Desk",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                sentiment_label="positive",
                importance_score=72.1,
                asset_symbols=["BTCUSDT"],
                contradiction_signals=[],
            ),
            FeedNewsRow(
                id="n2",
                title="Risk warning remains",
                summary="Summary",
                url="https://example.com/2",
                source_name="Desk",
                published_at=datetime(2026, 1, 1, tzinfo=UTC),
                sentiment_label="negative",
                importance_score=60.2,
                asset_symbols=["BTCUSDT"],
                contradiction_signals=[
                    {
                        "asset_symbol": "BTCUSDT",
                        "price_change_pct_24h": -1.4,
                        "is_contradiction": True,
                    }
                ],
            ),
        ]


def test_trade_idea_service_generates_explainable_thesis() -> None:
    service = TradeIdeaService(analysis_service=_FakeAnalysisService(), news_service=_FakeNewsService())  # type: ignore[arg-type]
    thesis = service.generate_thesis(
        symbol="BTCUSDT",
        timeframe="1h",
        asset_class="crypto",
        candle_limit=300,
        news_limit=20,
        news_hours=72,
    )

    assert thesis.setup_direction == "bullish"
    assert thesis.setup_type == "pullback_continuation"
    assert len(thesis.supporting_factors) > 0
    assert len(thesis.contradictory_factors) > 0
    assert thesis.invalidation.condition != ""
    assert thesis.confidence.explanation != ""
    assert "Informational only" in thesis.disclaimer
    assert "not a prediction" in thesis.thesis_summary
    assert thesis.confidence.score <= 84.0
