from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import pandas as pd

from prediction_lab.commoncrawl_evidence import (
    CommonCrawlCapture,
    CommonCrawlClient,
    HistoricalEvidenceError,
    _url_variants,
    select_parent_event_pilot,
)
from prediction_lab.datasets import verify_frozen_dataset
from prediction_lab.research_types import EvidenceItem

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_STOP_WORDS = {
    "will",
    "would",
    "what",
    "when",
    "where",
    "which",
    "with",
    "from",
    "into",
    "than",
    "this",
    "that",
    "have",
    "has",
    "been",
    "being",
    "before",
    "after",
    "over",
    "under",
    "above",
    "below",
    "between",
    "market",
    "price",
    "reach",
    "close",
    "higher",
    "lower",
    "more",
    "less",
    "yes",
    "event",
    "best",
    "month",
    "one",
    "day",
    "fdv",
    "launch",
    "launched",
    "token",
    "tokens",
    "committed",
    "public",
    "sale",
    "hit",
    "dip",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
_CRYPTO_CONTEXT_MARKERS = {
    "bitcoin",
    "blockchain",
    "crypto",
    "cryptocurrency",
    "ethereum",
    "fdv",
    "token",
    "tokens",
    "launch",
    "launched",
    "auction",
}
_MAJOR_CRYPTO_ASSETS = {"bitcoin", "ethereum", "zcash"}
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{2,}")


@dataclass(frozen=True)
class GdeltArticle:
    title: str
    url: str
    seen_at: pd.Timestamp
    domain: str
    language: str
    source_country: str


class NewsDiscovery(Protocol):
    def search(
        self,
        question_text: str,
        *,
        cutoff: pd.Timestamp,
        lookback_days: int,
        max_records: int,
    ) -> list[GdeltArticle]: ...


class ArchiveLookup(Protocol):
    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int,
    ) -> CommonCrawlCapture | None: ...

    def fetch_capture_text(
        self,
        capture: CommonCrawlCapture,
        *,
        max_characters: int,
    ) -> tuple[str, str]: ...


def _utc(value: object, *, field: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalEvidenceError(f"Invalid {field}: {value!r}") from exc
    if pd.isna(result):
        raise HistoricalEvidenceError(f"Missing {field}")
    if result.tzinfo is None:
        return result.tz_localize("UTC")
    return result.tz_convert("UTC")


def _parse_gdelt_seen(value: object) -> pd.Timestamp:
    text = str(value or "").strip()
    if not text:
        raise HistoricalEvidenceError("GDELT article is missing seendate")
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return pd.Timestamp(datetime.strptime(text, pattern), tz="UTC")
        except ValueError:
            continue
    return _utc(text, field="GDELT seendate")


def _query_terms(question_text: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for token in _TOKEN_RE.findall(question_text):
        cleaned = token.strip("._+-")
        normalized = cleaned.lower()
        if (
            len(normalized) < 3
            or normalized in _STOP_WORDS
            or normalized in seen
            or normalized[0].isdigit()
        ):
            continue
        seen.add(normalized)
        terms.append(cleaned)
    return terms


def build_gdelt_query(question_text: str, *, max_terms: int = 5) -> str:
    """Create a deterministic, outcome-blind, entity-first GDELT query.

    GDELT separates query terms with implicit AND semantics. Prediction-market
    titles often contain thresholds, deadlines, and market jargon that are not
    present verbatim in reporting, so requiring many title terms destroys
    recall. Anchor on the first useful entity and add only a broad crypto
    context block when the question itself is crypto-specific.
    """
    if max_terms < 1:
        raise ValueError("max_terms must be at least 1")
    terms = _query_terms(question_text)
    if not terms:
        raise HistoricalEvidenceError(
            f"Could not derive a useful GDELT query from question: {question_text!r}"
        )
    anchor = terms[0]
    question_tokens = {token.lower() for token in _TOKEN_RE.findall(question_text)}
    if anchor.lower() in _MAJOR_CRYPTO_ASSETS:
        return anchor
    if question_tokens & _CRYPTO_CONTEXT_MARKERS:
        return f'{anchor} (token OR crypto OR blockchain)'
    supporting = terms[1:max_terms]
    if not supporting:
        return anchor
    return f"{anchor} ({' OR '.join(supporting)})"


class GdeltDocClient:
    """Historical discovery only. GDELT result text is never used as evidence."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = GDELT_DOC_URL,
        timeout_seconds: float = 30.0,
        retries: int = 5,
        retry_backoff_seconds: float = 2.0,
        minimum_interval_seconds: float = 5.0,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        if retry_backoff_seconds < 0 or minimum_interval_seconds < 0:
            raise ValueError("retry and pacing intervals cannot be negative")
        self.endpoint = endpoint
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_request_at: float | None = None
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self._headers = {"User-Agent": "trading-prediction-lab/0.1 historical-news-research"}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GdeltDocClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _pace(self) -> None:
        if self._last_request_at is None or self.minimum_interval_seconds == 0:
            return
        remaining = self.minimum_interval_seconds - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _request(self, params: dict[str, object]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self._pace()
            try:
                response = self._client.get(self.endpoint, params=params, headers=self._headers)
                self._last_request_at = time.monotonic()
                if response.status_code == 200:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise HistoricalEvidenceError("GDELT returned non-object JSON")
                    return payload
                if response.status_code < 500 and response.status_code != 429:
                    raise HistoricalEvidenceError(
                        f"GDELT returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                last_error = HistoricalEvidenceError(
                    f"GDELT returned transient HTTP {response.status_code}"
                )
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        retry_delay = min(60.0, max(0.0, float(retry_after)))
                    except ValueError:
                        retry_delay = self.retry_backoff_seconds * (2**attempt)
                else:
                    retry_delay = self.retry_backoff_seconds * (2**attempt)
            except (httpx.HTTPError, ValueError) as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                retry_delay = self.retry_backoff_seconds * (2**attempt)
            if attempt + 1 < self.retries and retry_delay > 0:
                time.sleep(retry_delay)
        raise HistoricalEvidenceError(f"GDELT request failed: {last_error}")

    def search(
        self,
        question_text: str,
        *,
        cutoff: pd.Timestamp,
        lookback_days: int = 45,
        max_records: int = 20,
    ) -> list[GdeltArticle]:
        cutoff_at = _utc(cutoff, field="forecast cutoff")
        if lookback_days < 1:
            raise ValueError("lookback_days must be positive")
        if not 1 <= max_records <= 250:
            raise ValueError("max_records must be between 1 and 250")
        start = cutoff_at - pd.Timedelta(days=lookback_days)
        query = build_gdelt_query(question_text)
        payload = self._request(
            {
                "query": query,
                "mode": "artlist",
                "maxrecords": max_records,
                "format": "json",
                "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                "enddatetime": cutoff_at.strftime("%Y%m%d%H%M%S"),
                "sort": "datedesc",
            }
        )
        raw_articles = payload.get("articles", [])
        if not isinstance(raw_articles, list):
            raise HistoricalEvidenceError("GDELT articles field is not a list")

        articles: list[GdeltArticle] = []
        seen_urls: set[str] = set()
        for raw in raw_articles:
            if not isinstance(raw, dict) or not raw.get("url") or not raw.get("title"):
                continue
            try:
                seen_at = _parse_gdelt_seen(raw.get("seendate"))
            except HistoricalEvidenceError:
                continue
            if seen_at > cutoff_at:
                continue
            url = str(raw["url"])
            if url in seen_urls:
                continue
            seen_urls.add(url)
            articles.append(
                GdeltArticle(
                    title=str(raw["title"]),
                    url=url,
                    seen_at=seen_at,
                    domain=str(raw.get("domain") or urlparse(url).netloc),
                    language=str(raw.get("language") or "unknown"),
                    source_country=str(raw.get("sourcecountry") or "unknown"),
                )
            )
        articles.sort(key=lambda article: article.seen_at, reverse=True)
        return articles


class FastCommonCrawlClient(CommonCrawlClient):
    """Common Crawl lookup that exits as soon as the newest valid exact-page capture is found."""

    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int = 3,
    ) -> CommonCrawlCapture | None:
        cutoff_at = _utc(cutoff, field="capture cutoff")
        requested_path = urlparse(url).path or "/"
        variants = [
            variant
            for variant in _url_variants(url)
            if (urlparse(variant).path or "/") == requested_path
        ]
        transport_errors: list[str] = []
        for collection in self._eligible_collections(  # type: ignore[attr-defined]
            cutoff_at,
            max_collections=max_collections,
        ):
            crawl_id = str(collection["id"])
            endpoint = str(
                collection.get("cdx-api") or f"{self.index_url}/{crawl_id}-index"
            )
            for variant in variants:
                try:
                    response = self._get(  # type: ignore[attr-defined]
                        endpoint,
                        params={"url": variant, "output": "json"},
                        headers=self._headers,  # type: ignore[attr-defined]
                    )
                except (HistoricalEvidenceError, httpx.HTTPError) as exc:
                    transport_errors.append(f"{variant}: {exc}")
                    continue
                if response.status_code == 404:
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    transport_errors.append(
                        f"{variant}: Common Crawl HTTP {response.status_code} after retries"
                    )
                    continue
                response.raise_for_status()
                valid: list[CommonCrawlCapture] = []
                for line in response.text.splitlines():
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    try:
                        capture = CommonCrawlCapture.from_record(crawl_id, record)
                    except HistoricalEvidenceError:
                        continue
                    if (
                        capture.timestamp <= cutoff_at
                        and capture.status == "200"
                        and "html" in capture.mime.lower()
                    ):
                        valid.append(capture)
                if valid:
                    return max(valid, key=lambda capture: capture.timestamp)
        if transport_errors:
            detail = " | ".join(transport_errors[:3])
            raise HistoricalEvidenceError(
                f"Common Crawl lookup exhausted with transport errors: {detail}"
            )
        return None


def build_gdelt_commoncrawl_pilot(
    *,
    development_csv: str | Path,
    development_manifest: str | Path,
    discovery: NewsDiscovery,
    archive: ArchiveLookup,
    pilot_size: int = 20,
    lookback_days: int = 45,
    max_discovery_records: int = 20,
    max_article_urls: int = 6,
    max_evidence_items: int = 2,
    max_collections: int = 3,
    max_characters_per_item: int = 10_000,
) -> tuple[dict[str, object], dict[str, object], pd.DataFrame]:
    """Build a development-only pilot with dual timestamp validation."""
    development = verify_frozen_dataset(
        csv_path=development_csv,
        manifest_path=development_manifest,
    )
    split_values = set(development.get("split", pd.Series(dtype=str)).astype(str))
    if split_values != {"development"}:
        raise HistoricalEvidenceError("Historical news pilot accepts development rows only")

    pilot = select_parent_event_pilot(development, size=pilot_size)
    questions: dict[str, list[dict[str, object]]] = {}
    audit_rows: list[dict[str, object]] = []
    domains: Counter[str] = Counter()
    retrieved_at = datetime.now(UTC).isoformat()

    for row in pilot.itertuples(index=False):
        question_id = str(row.question_id)
        question_text = str(row.question_text)
        cutoff = _utc(row.source_cutoff_at, field="source_cutoff_at")
        evidence: list[EvidenceItem] = []
        seen_digests: set[str] = set()
        errors: list[str] = []
        try:
            articles = discovery.search(
                question_text,
                cutoff=cutoff,
                lookback_days=lookback_days,
                max_records=max_discovery_records,
            )
        except (HistoricalEvidenceError, httpx.HTTPError) as exc:
            articles = []
            errors.append(f"discovery: {exc}")

        attempted_urls = 0
        for article in articles[:max_article_urls]:
            if len(evidence) >= max_evidence_items:
                break
            attempted_urls += 1
            try:
                capture = archive.latest_capture_before(
                    article.url,
                    cutoff=cutoff,
                    max_collections=max_collections,
                )
            except (HistoricalEvidenceError, httpx.HTTPError) as exc:
                errors.append(f"archive lookup {article.url}: {exc}")
                continue
            if capture is None or capture.digest in seen_digests:
                continue
            if capture.timestamp > cutoff or article.seen_at > cutoff:
                raise HistoricalEvidenceError("Post-cutoff news evidence escaped filtering")
            try:
                text, archived_title = archive.fetch_capture_text(
                    capture,
                    max_characters=max_characters_per_item,
                )
            except (HistoricalEvidenceError, httpx.HTTPError) as exc:
                errors.append(f"archive fetch {article.url}: {exc}")
                continue

            available_at = max(capture.timestamp, article.seen_at)
            if available_at > cutoff:
                raise HistoricalEvidenceError("Derived evidence availability exceeds cutoff")
            seen_digests.add(capture.digest)
            domain = urlparse(capture.url).netloc.lower()
            domains[domain] += 1
            evidence.append(
                EvidenceItem.create(
                    source_id=f"gdelt-cc:{capture.crawl_id}:{capture.digest}",
                    source_type="gdelt-discovered-common-crawl-warc",
                    uri_or_reference=(
                        f"commoncrawl://{capture.crawl_id}/{capture.filename}"
                        f"#{capture.offset}:{capture.length}"
                    ),
                    title=archived_title or article.title,
                    available_at=available_at.isoformat(),
                    retrieved_at=retrieved_at,
                    text=text,
                )
            )

        questions[question_id] = [item.to_dict() for item in evidence]
        latest = max((item.available_at for item in evidence), default=None)
        age_hours = (
            (cutoff.to_pydatetime() - latest).total_seconds() / 3600.0
            if latest is not None
            else None
        )
        audit_rows.append(
            {
                "question_id": question_id,
                "question_text": question_text,
                "event_id": str(row.event_id),
                "forecasted_at": _utc(row.forecasted_at, field="forecasted_at").isoformat(),
                "discovered_article_count": len(articles),
                "attempted_article_urls": attempted_urls,
                "evidence_item_count": len(evidence),
                "latest_evidence_age_hours": age_hours,
                "errors": " | ".join(errors),
            }
        )

    audit = pd.DataFrame(audit_rows)
    covered = int((audit["evidence_item_count"] > 0).sum())
    discovered = int((audit["discovered_article_count"] > 0).sum())
    ages = pd.to_numeric(audit["latest_evidence_age_hours"], errors="coerce").dropna()
    summary: dict[str, object] = {
        "schema_version": 1,
        "pilot_size": len(audit),
        "parent_events": int(audit["event_id"].nunique()),
        "questions_with_gdelt_results": discovered,
        "questions_with_archived_evidence": covered,
        "coverage_rate": covered / len(audit) if len(audit) else 0.0,
        "total_evidence_items": int(audit["evidence_item_count"].sum()),
        "source_domains": dict(sorted(domains.items())),
        "zero_evidence_question_ids": audit.loc[
            audit["evidence_item_count"] == 0, "question_id"
        ].astype(str).tolist(),
        "latest_evidence_age_hours": {
            "min": float(ages.min()) if not ages.empty else None,
            "median": float(ages.median()) if not ages.empty else None,
            "max": float(ages.max()) if not ages.empty else None,
        },
        "discovery_policy": (
            "GDELT DOC entity-first query derived only from question text; requests paced "
            f"to respect rate limits; {lookback_days}-day lookback; up to "
            f"{max_discovery_records} results and {max_article_urls} archive attempts"
        ),
        "archive_policy": (
            "article content admitted only from exact-page Common Crawl HTTP-200 HTML "
            "captures whose capture timestamp and GDELT seen timestamp are both <= "
            f"source_cutoff_at; up to {max_collections} crawl collections and "
            f"{max_evidence_items} items"
        ),
        "selection_policy": (
            "time-spread first representative from each development parent event; "
            "selection does not consult outcomes or market probabilities"
        ),
    }
    return {"schema_version": 1, "questions": questions}, summary, audit
