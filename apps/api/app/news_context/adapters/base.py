from __future__ import annotations

from abc import ABC, abstractmethod

from app.news_context.domain import NewsCandidate


class NewsProviderAdapter(ABC):
    provider_code: str

    @abstractmethod
    def fetch_news(self, *, limit: int, symbols: list[str] | None = None) -> list[NewsCandidate]:
        raise NotImplementedError
