from __future__ import annotations

import re

from app.news_context.domain import NewsCandidate, TaggedAsset
from app.repositories.news_context_repository import AssetRef


def tag_assets(candidate: NewsCandidate, assets: list[AssetRef]) -> list[TaggedAsset]:
    if not assets:
        return []

    text = _normalize(f"{candidate.title} {candidate.summary}")
    provider_tickers = {ticker.upper() for ticker in candidate.provider_tickers}

    tagged: list[TaggedAsset] = []
    for asset in assets:
        score = 0.0
        normalized_symbol = asset.normalized_symbol.upper()
        display_pair = asset.display_symbol.replace("/", "").upper()

        if normalized_symbol in provider_tickers:
            score = max(score, 0.95)
        if asset.base_currency.upper() in provider_tickers:
            score = max(score, 0.82)

        if normalized_symbol in text or display_pair in text:
            score = max(score, 0.9)
        if re.search(rf"\b{re.escape(asset.base_currency.upper())}\b", text):
            score = max(score, 0.6)
        if re.search(rf"\b{re.escape(asset.display_symbol.upper())}\b", text):
            score = max(score, 0.8)

        if score >= 0.35:
            tagged.append(
                TaggedAsset(
                    asset_id=str(asset.id),
                    normalized_symbol=asset.normalized_symbol,
                    relevance_score=round(score, 2),
                )
            )

    return sorted(tagged, key=lambda item: item.relevance_score, reverse=True)


def _normalize(value: str) -> str:
    upper = value.upper()
    collapsed = re.sub(r"\s+", " ", upper)
    return re.sub(r"[^A-Z0-9/]", " ", collapsed)
