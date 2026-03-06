from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.trade_ideas.domain import Confidence, Invalidation, TradeThesis
from app.trade_ideas.service import get_trade_idea_service


class _FakeTradeIdeaService:
    def generate_thesis(self, **kwargs) -> TradeThesis:  # type: ignore[no-untyped-def]
        _ = kwargs
        return TradeThesis(
            symbol="BTCUSDT",
            timeframe="1h",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            setup_direction="bullish",
            setup_type="breakout",
            supporting_factors=[
                "Price closed above resistance with momentum confirmation.",
                "Recent sentiment leans positive.",
            ],
            contradictory_factors=[
                "One contradictory news/price signal is present.",
            ],
            invalidation=Invalidation(
                level=102.8,
                condition="Invalidate if price closes below 102.800000.",
            ),
            confidence=Confidence(
                label="medium",
                score=66.2,
                explanation="Confidence is medium and explicitly uncertain due to mixed context.",
            ),
            thesis_summary=(
                "BTCUSDT 1h: bullish thesis from breakout with medium confidence. "
                "View this as a conditional scenario, not a prediction."
            ),
            disclaimer="Informational only. This is not financial advice.",
        )


def test_trade_ideas_generate_endpoint() -> None:
    app.dependency_overrides[get_trade_idea_service] = lambda: _FakeTradeIdeaService()
    client = TestClient(app)
    response = client.post(
        "/api/v1/trade-ideas/generate",
        json={
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "asset_class": "crypto",
            "candle_limit": 300,
            "news_limit": 20,
            "news_hours": 72,
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["setup_direction"] == "bullish"
    assert "supporting_factors" in body
    assert "contradictory_factors" in body
    assert "invalidation" in body
    assert "confidence" in body
    assert "Informational only" in body["disclaimer"]
