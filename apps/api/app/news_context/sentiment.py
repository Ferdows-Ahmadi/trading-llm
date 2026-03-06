from __future__ import annotations

import re

from app.news_context.domain import NewsCandidate

_POSITIVE_TERMS = {
    "bullish",
    "surge",
    "rally",
    "breakout",
    "upgrade",
    "beats",
    "optimistic",
    "growth",
    "gain",
}
_NEGATIVE_TERMS = {
    "bearish",
    "selloff",
    "drop",
    "downgrade",
    "misses",
    "lawsuit",
    "fraud",
    "risk",
    "loss",
}


def label_sentiment(candidate: NewsCandidate) -> tuple[str, float]:
    if candidate.provider_sentiment_label:
        label = candidate.provider_sentiment_label.lower()
        if "bull" in label or "positive" in label:
            return ("positive", candidate.provider_sentiment_score or 0.25)
        if "bear" in label or "negative" in label:
            return ("negative", candidate.provider_sentiment_score or -0.25)
        return ("neutral", candidate.provider_sentiment_score or 0.0)

    text = _normalize(f"{candidate.title} {candidate.summary}")
    positive_hits = sum(1 for term in _POSITIVE_TERMS if term in text)
    negative_hits = sum(1 for term in _NEGATIVE_TERMS if term in text)
    score = (positive_hits - negative_hits) / max(positive_hits + negative_hits, 1)

    if score >= 0.2:
        return ("positive", score)
    if score <= -0.2:
        return ("negative", score)
    return ("neutral", score)


def _normalize(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    return re.sub(r"[^a-z0-9 ]", "", normalized)
