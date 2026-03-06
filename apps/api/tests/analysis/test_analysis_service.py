from __future__ import annotations

from app.analysis.service import AnalysisService
from tests.analysis.utils import make_trending_candles


class _FakeRepository:
    def list_candles(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return make_trending_candles(count=320)


def test_analysis_service_returns_scored_result() -> None:
    service = AnalysisService(repository=_FakeRepository())  # type: ignore[arg-type]
    result = service.analyze_asset(
        raw_symbol="BTC/USDT",
        timeframe="1h",
        limit=300,
        asset_class="crypto",
    )

    assert result.symbol == "BTCUSDT"
    assert result.candle_count >= 300
    assert "ema_20" in result.latest_indicators
    assert result.score.total_score >= 0
