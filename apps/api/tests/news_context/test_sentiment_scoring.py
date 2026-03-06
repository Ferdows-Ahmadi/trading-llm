from datetime import UTC, datetime, timedelta

from app.news_context.domain import NewsCandidate
from app.news_context.scoring import score_importance
from app.news_context.sentiment import label_sentiment


def test_sentiment_labeling_without_provider_signal() -> None:
    candidate = NewsCandidate(
        external_id=None,
        source_name="Desk",
        title="Bitcoin bullish breakout after strong growth data",
        summary="Analysts optimistic as markets rally.",
        url="https://example.com/news",
        published_at=datetime.now(tz=UTC),
    )
    label, score = label_sentiment(candidate)
    assert label == "positive"
    assert score > 0


def test_importance_scoring_bounds() -> None:
    candidate = NewsCandidate(
        external_id=None,
        source_name="Desk",
        title="Macro risk increases for forex pairs",
        summary="Some loss signals appear in markets.",
        url="https://example.com/news2",
        published_at=datetime.now(tz=UTC) - timedelta(hours=4),
        provider_importance=0.6,
    )
    importance = score_importance(candidate=candidate, sentiment_score=-0.4, relevance_scores=[0.7, 0.4])
    assert 0 <= importance <= 100
