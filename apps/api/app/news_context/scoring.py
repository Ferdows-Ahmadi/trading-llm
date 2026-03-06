from __future__ import annotations

from datetime import UTC, datetime

from app.news_context.domain import NewsCandidate


def score_importance(
    *,
    candidate: NewsCandidate,
    sentiment_score: float,
    relevance_scores: list[float],
) -> float:
    now = datetime.now(tz=UTC)
    age_hours = max((now - candidate.published_at).total_seconds() / 3600.0, 0.0)
    recency_score = max(0.0, 25.0 - (age_hours * 1.1))
    sentiment_intensity = min(abs(sentiment_score) * 30.0, 25.0)
    relevance_score = min((max(relevance_scores) if relevance_scores else 0.0) * 25.0, 25.0)
    provider_score = (
        min(max(candidate.provider_importance or 0.0, 0.0), 1.0) * 20.0
        if candidate.provider_importance is not None
        else 8.0
    )
    total = 20.0 + recency_score + sentiment_intensity + relevance_score + provider_score
    return round(max(0.0, min(total, 100.0)), 2)
