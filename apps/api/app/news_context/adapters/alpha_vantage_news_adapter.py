from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app.market_data.resilience.executor import ResilienceExecutor
from app.news_context.adapters.base import NewsProviderAdapter
from app.news_context.domain import NewsCandidate
from app.news_context.exceptions import NewsProviderError

_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageNewsAdapter(NewsProviderAdapter):
    provider_code = "alpha_vantage"

    def __init__(
        self,
        *,
        api_key: str,
        resilience: ResilienceExecutor[list[NewsCandidate]],
        http_client_factory: Callable[[], httpx.Client] | None = None,
        default_rate_limit_per_minute: int = 5,
        default_cache_ttl_seconds: int = 120,
    ) -> None:
        if not api_key:
            raise NewsProviderError("ALPHAVANTAGE_API_KEY is required for alpha_vantage news adapter")
        self._api_key = api_key
        self._resilience = resilience
        self._http_client_factory = http_client_factory or self._default_http_client
        self._default_rate_limit_per_minute = default_rate_limit_per_minute
        self._default_cache_ttl_seconds = default_cache_ttl_seconds

    def fetch_news(self, *, limit: int, symbols: list[str] | None = None) -> list[NewsCandidate]:
        ticker_filter = ",".join(symbols) if symbols else ""
        cache_key = f"{self.provider_code}:news:{ticker_filter}:{limit}"
        params = {
            "function": "NEWS_SENTIMENT",
            "sort": "LATEST",
            "limit": str(limit),
            "apikey": self._api_key,
        }
        if ticker_filter:
            params["tickers"] = ticker_filter

        def _call_provider() -> list[NewsCandidate]:
            try:
                with self._http_client_factory() as client:
                    response = client.get(_BASE_URL, params=params)
                    response.raise_for_status()
            except Exception as exc:
                raise NewsProviderError(f"Alpha Vantage news request failed: {exc}") from exc

            payload = response.json()
            self._raise_for_provider_messages(payload)
            return _payload_to_candidates(payload)

        candidates = self._resilience.execute(
            provider_code=self.provider_code,
            cache_key=cache_key,
            operation=_call_provider,
            cache_ttl_seconds=self._default_cache_ttl_seconds,
            rate_limit_per_minute=self._default_rate_limit_per_minute,
            retry_exceptions=(NewsProviderError,),
        )
        return candidates[:limit]

    @staticmethod
    def _raise_for_provider_messages(payload: dict[str, Any]) -> None:
        for field in ("Error Message", "Information", "Note"):
            if field in payload:
                raise NewsProviderError(f"Alpha Vantage error: {payload[field]}")

    @staticmethod
    def _default_http_client() -> httpx.Client:
        return httpx.Client(timeout=20.0)


def _payload_to_candidates(payload: dict[str, Any]) -> list[NewsCandidate]:
    raw_feed = payload.get("feed")
    if not isinstance(raw_feed, list):
        raise NewsProviderError("Alpha Vantage response did not include a feed array")

    parsed: list[NewsCandidate] = []
    for item in raw_feed:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title", "")).strip()
        if not title:
            continue

        summary = str(item.get("summary", "")).strip()
        url = str(item.get("url", "")).strip()
        source = str(item.get("source", "unknown")).strip() or "unknown"
        published = _parse_published(item.get("time_published"))
        external_id = str(item.get("id", "")).strip() or None
        provider_score = _safe_float(item.get("overall_sentiment_score"))
        provider_label = str(item.get("overall_sentiment_label", "")).strip() or None
        tickers = _extract_tickers(item.get("ticker_sentiment"))

        parsed.append(
            NewsCandidate(
                external_id=external_id,
                source_name=source,
                title=title,
                summary=summary,
                url=url,
                published_at=published,
                provider_sentiment_score=provider_score,
                provider_sentiment_label=provider_label,
                provider_tickers=tickers,
                raw_payload=item,
            )
        )
    return parsed


def _parse_published(raw_value: object) -> datetime:
    raw = str(raw_value or "").strip()
    if not raw:
        return datetime.now(tz=UTC)
    try:
        if len(raw) >= 15:
            return datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        return datetime.strptime(raw[:8], "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(tz=UTC)


def _extract_tickers(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    output: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker", "")).strip().upper()
        if ticker:
            output.append(ticker)
    return output


def _safe_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
