from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import cast

from app.analysis.domain import AnalysisResult, SetupSignal
from app.analysis.exceptions import AnalysisError
from app.analysis.service import AnalysisService, get_analysis_service
from app.market_data.domain import AssetClass
from app.news_context.exceptions import NewsContextError
from app.news_context.service import NewsContextService, get_news_context_service
from app.repositories.news_context_repository import FeedNewsRow
from app.trade_ideas.domain import Confidence, ConfidenceLabel, Invalidation, TradeDirection, TradeThesis
from app.trade_ideas.exceptions import TradeIdeaError

_DISCLAIMER = (
    "Informational only. This thesis is a probabilistic interpretation of historical data and current context, "
    "not financial advice."
)


class TradeIdeaService:
    def __init__(self, analysis_service: AnalysisService, news_service: NewsContextService) -> None:
        self._analysis_service = analysis_service
        self._news_service = news_service

    def generate_thesis(
        self,
        *,
        symbol: str,
        timeframe: str,
        asset_class: str | None,
        candle_limit: int,
        news_limit: int,
        news_hours: int,
    ) -> TradeThesis:
        typed_asset_class = cast(AssetClass | None, asset_class)
        try:
            analysis = self._analysis_service.analyze_asset(
                raw_symbol=symbol,
                timeframe=timeframe,
                limit=candle_limit,
                asset_class=typed_asset_class,
            )
            news_rows = self._news_service.list_feed(
                limit=news_limit,
                hours=news_hours,
                symbol=symbol,
                asset_class=typed_asset_class,
            )
        except (AnalysisError, NewsContextError) as exc:
            raise TradeIdeaError(str(exc)) from exc

        primary_setup = _pick_primary_setup(analysis)
        direction = _resolve_direction(analysis, primary_setup)
        supporting_factors = _build_supporting_factors(analysis, news_rows, primary_setup, direction)
        contradictory_factors = _build_contradictory_factors(analysis, news_rows, primary_setup, direction)
        invalidation = _resolve_invalidation(analysis, primary_setup, direction)
        confidence = _build_confidence(analysis, primary_setup, contradictory_factors)
        summary = _build_summary(analysis, primary_setup, confidence, direction, contradictory_factors)

        return TradeThesis(
            symbol=analysis.symbol,
            timeframe=analysis.timeframe,
            generated_at=datetime.now(tz=UTC),
            setup_direction=direction,
            setup_type=primary_setup.setup_type if primary_setup is not None else None,
            supporting_factors=supporting_factors,
            contradictory_factors=contradictory_factors,
            invalidation=invalidation,
            confidence=confidence,
            thesis_summary=summary,
            disclaimer=_DISCLAIMER,
        )


def _pick_primary_setup(analysis: AnalysisResult) -> SetupSignal | None:
    triggered = [setup for setup in analysis.setups if setup.triggered]
    if triggered:
        return max(triggered, key=lambda setup: setup.score)
    if analysis.setups:
        return max(analysis.setups, key=lambda setup: setup.score)
    return None


def _resolve_direction(analysis: AnalysisResult, setup: SetupSignal | None) -> TradeDirection:
    if setup is not None:
        return setup.direction
    if analysis.trend_regime.label == "bull_trend":
        return "bullish"
    if analysis.trend_regime.label == "bear_trend":
        return "bearish"
    return "neutral"


def _build_supporting_factors(
    analysis: AnalysisResult,
    news_rows: list[FeedNewsRow],
    setup: SetupSignal | None,
    direction: TradeDirection,
) -> list[str]:
    factors: list[str] = []
    if setup is not None:
        factors.extend(setup.reasons[:2])

    regime = analysis.trend_regime
    if direction == "bullish" and regime.label == "bull_trend":
        factors.append(f"Trend regime is bullish with confidence {regime.confidence:.2f}.")
    elif direction == "bearish" and regime.label == "bear_trend":
        factors.append(f"Trend regime is bearish with confidence {regime.confidence:.2f}.")
    elif regime.label in {"range", "range_compression"}:
        factors.append("Range regime supports selective mean-reversion setups.")

    indicators = analysis.latest_indicators
    ema20 = indicators.get("ema_20")
    ema50 = indicators.get("ema_50")
    ema200 = indicators.get("ema_200")
    rsi = indicators.get("rsi_14")
    macd_hist = indicators.get("macd_hist")

    if direction == "bullish" and _is_ema_bull_stack(ema20, ema50, ema200):
        factors.append("EMA alignment (20 > 50 > 200) supports upside structure.")
    if direction == "bearish" and _is_ema_bear_stack(ema20, ema50, ema200):
        factors.append("EMA alignment (20 < 50 < 200) supports downside structure.")
    if rsi is not None:
        factors.append(f"RSI(14) at {rsi:.2f} is incorporated into momentum context.")
    if macd_hist is not None:
        factors.append(f"MACD histogram currently {macd_hist:.4f}.")

    sentiment_snapshot = _news_sentiment_snapshot(news_rows, direction=direction)
    if sentiment_snapshot:
        factors.append(sentiment_snapshot)

    return factors[:6]


def _build_contradictory_factors(
    analysis: AnalysisResult,
    news_rows: list[FeedNewsRow],
    setup: SetupSignal | None,
    direction: TradeDirection,
) -> list[str]:
    factors: list[str] = []
    regime = analysis.trend_regime

    if regime.label in {"range", "range_compression", "transition"}:
        factors.append(f"Regime is {regime.label}, which can weaken directional follow-through.")

    opposing = [candidate for candidate in analysis.setups if setup is None or candidate is not setup]
    for candidate in opposing:
        if candidate.direction != direction and candidate.triggered:
            factors.append(
                f"Opposing {candidate.setup_type} setup is also triggered ({candidate.direction})."
            )
            break

    rsi = analysis.latest_indicators.get("rsi_14")
    if rsi is not None:
        if direction == "bullish" and rsi >= 70:
            factors.append("RSI is in overbought territory, raising pullback risk.")
        elif direction == "bearish" and rsi <= 30:
            factors.append("RSI is in oversold territory, raising squeeze risk.")

    contradiction_count = 0
    for row in news_rows:
        for signal in row.contradiction_signals:
            if bool(signal.get("is_contradiction")):
                contradiction_count += 1
    if contradiction_count > 0:
        factors.append(
            f"{contradiction_count} recent news items show sentiment/price contradiction signals."
        )

    aligned_negative_news = _opposing_news_summary(news_rows, direction)
    if aligned_negative_news:
        factors.append(aligned_negative_news)

    return factors[:6]


def _resolve_invalidation(
    analysis: AnalysisResult,
    setup: SetupSignal | None,
    direction: TradeDirection,
) -> Invalidation:
    if setup is not None and setup.stop_hint is not None:
        condition = (
            f"Invalidate if price closes below {setup.stop_hint:.6f}."
            if direction == "bullish"
            else f"Invalidate if price closes above {setup.stop_hint:.6f}."
            if direction == "bearish"
            else f"Invalidate if price closes beyond {setup.stop_hint:.6f}."
        )
        return Invalidation(level=round(setup.stop_hint, 8), condition=condition)

    if direction == "bullish" and analysis.supports:
        level = analysis.supports[0].level
        return Invalidation(
            level=level,
            condition=f"Invalidate if price loses support near {level:.6f}.",
        )
    if direction == "bearish" and analysis.resistances:
        level = analysis.resistances[0].level
        return Invalidation(
            level=level,
            condition=f"Invalidate if price reclaims resistance near {level:.6f}.",
        )

    if analysis.resistances and analysis.supports:
        resistance = analysis.resistances[0].level
        support = analysis.supports[0].level
        return Invalidation(
            level=None,
            condition=(
                f"No directional thesis until price breaks above {resistance:.6f} "
                f"or below {support:.6f}."
            ),
        )

    return Invalidation(level=None, condition="Insufficient structure for a precise invalidation level.")


def _build_confidence(
    analysis: AnalysisResult,
    setup: SetupSignal | None,
    contradictory_factors: list[str],
) -> Confidence:
    base = analysis.score.total_score
    if setup is not None:
        base = (0.7 * base) + (0.3 * setup.score)

    penalty = len(contradictory_factors) * 6.0
    if analysis.trend_regime.label in {"range", "range_compression", "transition"}:
        penalty += 6.0
    if analysis.trend_regime.label == "insufficient_data":
        penalty += 18.0

    score = max(10.0, min(base - penalty, 84.0))
    label: ConfidenceLabel
    if score < 45:
        label = "low"
    elif score < 70:
        label = "medium"
    else:
        label = "high"

    explanation = (
        f"Confidence is {label} ({score:.1f}/100) based on deterministic technical and context signals; "
        f"{len(contradictory_factors)} contradiction factor(s) reduce certainty."
    )
    return Confidence(label=label, score=round(score, 2), explanation=explanation)


def _build_summary(
    analysis: AnalysisResult,
    setup: SetupSignal | None,
    confidence: Confidence,
    direction: TradeDirection,
    contradictory_factors: list[str],
) -> str:
    setup_label = setup.setup_type if setup is not None else "no clear setup"
    return (
        f"{analysis.symbol} {analysis.timeframe}: {direction} thesis from {setup_label} with "
        f"{confidence.label} confidence. View this as a conditional scenario, not a prediction, "
        f"and monitor {len(contradictory_factors)} opposing signal(s)."
    )


def _is_ema_bull_stack(ema20: float | None, ema50: float | None, ema200: float | None) -> bool:
    return ema20 is not None and ema50 is not None and ema200 is not None and ema20 > ema50 > ema200


def _is_ema_bear_stack(ema20: float | None, ema50: float | None, ema200: float | None) -> bool:
    return ema20 is not None and ema50 is not None and ema200 is not None and ema20 < ema50 < ema200


def _news_sentiment_snapshot(news_rows: list[FeedNewsRow], direction: TradeDirection) -> str | None:
    if not news_rows:
        return None
    scored = [row for row in news_rows if row.sentiment_label is not None]
    if not scored:
        return None

    positive = sum(1 for row in scored if row.sentiment_label == "positive")
    negative = sum(1 for row in scored if row.sentiment_label == "negative")
    if direction == "bullish" and positive > negative:
        return f"Recent news sentiment leans positive ({positive} positive vs {negative} negative items)."
    if direction == "bearish" and negative > positive:
        return f"Recent news sentiment leans negative ({negative} negative vs {positive} positive items)."
    return f"Recent news sentiment is mixed ({positive} positive, {negative} negative)."


def _opposing_news_summary(news_rows: list[FeedNewsRow], direction: TradeDirection) -> str | None:
    if not news_rows:
        return None
    if direction == "bullish":
        opposing = sum(1 for row in news_rows if row.sentiment_label == "negative")
        if opposing > 0:
            return f"{opposing} negative news item(s) oppose the bullish thesis."
    if direction == "bearish":
        opposing = sum(1 for row in news_rows if row.sentiment_label == "positive")
        if opposing > 0:
            return f"{opposing} positive news item(s) oppose the bearish thesis."
    return None


_trade_idea_service_instance: TradeIdeaService | None = None


def get_trade_idea_service() -> TradeIdeaService:
    global _trade_idea_service_instance
    if _trade_idea_service_instance is None:
        _trade_idea_service_instance = TradeIdeaService(
            analysis_service=get_analysis_service(),
            news_service=get_news_context_service(),
        )
    return _trade_idea_service_instance


def serialize_trade_thesis(thesis: TradeThesis) -> dict[str, object]:
    payload = asdict(thesis)
    payload["generated_at"] = thesis.generated_at.isoformat()
    return payload


def reset_trade_idea_service_for_tests() -> None:
    global _trade_idea_service_instance
    _trade_idea_service_instance = None
