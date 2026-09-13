from __future__ import annotations

import io
import json
import re
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

import httpx
import numpy as np
import pandas as pd
from warcio.archiveiterator import ArchiveIterator  # type: ignore[import-untyped]

from prediction_lab.datasets import verify_frozen_dataset
from prediction_lab.research_types import EvidenceItem

COMMON_CRAWL_INDEX = "https://index.commoncrawl.org"
COMMON_CRAWL_DATA = "https://data.commoncrawl.org"
_URL_PATTERN = re.compile(r"https?://[^\s\]\[(){}<>\"']+")
_TRAILING_URL_PUNCTUATION = ".,;:!?"


class HistoricalEvidenceError(RuntimeError):
    """Raised when timestamp-safe historical evidence cannot be constructed."""


@dataclass(frozen=True)
class CommonCrawlCapture:
    crawl_id: str
    timestamp: pd.Timestamp
    url: str
    digest: str
    filename: str
    offset: int
    length: int
    mime: str
    status: str

    @classmethod
    def from_record(cls, crawl_id: str, record: dict[str, Any]) -> CommonCrawlCapture:
        try:
            timestamp = pd.to_datetime(
                str(record["timestamp"]),
                format="%Y%m%d%H%M%S",
                utc=True,
            )
            return cls(
                crawl_id=crawl_id,
                timestamp=timestamp,
                url=str(record["url"]),
                digest=str(record["digest"]),
                filename=str(record["filename"]),
                offset=int(record["offset"]),
                length=int(record["length"]),
                mime=str(record.get("mime-detected") or record.get("mime") or ""),
                status=str(record.get("status") or ""),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoricalEvidenceError("Malformed Common Crawl capture record") from exc

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._title_depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._skip_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "template"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title" and self._title_depth:
            self._title_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        self.parts.append(text)
        self.parts.append(" ")
        if self._title_depth:
            self.title_parts.append(text)

    def visible_text(self) -> str:
        text = "".join(self.parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        return "\n".join(line for line in lines if line)

    def title(self) -> str:
        return " ".join(" ".join(self.title_parts).split())


def _utc_timestamp(value: object, *, field: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(cast(str, value))
    except (TypeError, ValueError) as exc:
        raise HistoricalEvidenceError(f"Invalid {field}: {value!r}") from exc
    if pd.isna(timestamp):
        raise HistoricalEvidenceError(f"Missing {field}")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _clean_url(value: str) -> str | None:
    candidate = value.rstrip(_TRAILING_URL_PUNCTUATION)
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.netloc.lower().endswith("polymarket.com"):
        return None
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )


def extract_reference_urls(market: dict[str, Any]) -> list[str]:
    """Extract locator URLs from frozen Polymarket metadata without using it as evidence."""
    text_fields = [
        str(market.get("description") or ""),
        str(market.get("resolutionSource") or ""),
    ]
    events = market.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                text_fields.extend(
                    [
                        str(event.get("description") or ""),
                        str(event.get("resolutionSource") or ""),
                    ]
                )

    urls: list[str] = []
    seen: set[str] = set()
    for raw in _URL_PATTERN.findall("\n".join(text_fields)):
        cleaned = _clean_url(raw)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls


def select_parent_event_pilot(cases: pd.DataFrame, *, size: int = 20) -> pd.DataFrame:
    """Choose time-spread representatives without consulting outcomes or market probabilities."""
    if size < 1:
        raise ValueError("size must be positive")
    required = {
        "question_id",
        "question_text",
        "forecasted_at",
        "source_cutoff_at",
        "event_id",
    }
    missing = sorted(required - set(cases.columns))
    if missing:
        raise HistoricalEvidenceError(f"Development dataset is missing columns: {missing}")

    safe = cases[list(required)].copy()
    safe["forecasted_at"] = pd.to_datetime(safe["forecasted_at"], utc=True, errors="raise")
    safe["source_cutoff_at"] = pd.to_datetime(safe["source_cutoff_at"], utc=True, errors="raise")
    safe.sort_values(["forecasted_at", "question_id"], inplace=True)
    representatives = safe.drop_duplicates("event_id", keep="first").reset_index(drop=True)
    if len(representatives) <= size:
        return representatives
    positions = np.linspace(0, len(representatives) - 1, num=size, dtype=int)
    return representatives.iloc[positions].reset_index(drop=True)


def load_market_records(path: str | Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    source = Path(path)
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HistoricalEvidenceError(f"Malformed market JSONL at line {line_number}") from exc
        if not isinstance(item, dict) or not item.get("id"):
            raise HistoricalEvidenceError(f"Market JSONL line {line_number} has no id")
        records[str(item["id"])] = item
    return records


def _url_variants(url: str) -> list[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path or "/"
    hosts = [host]
    if host.startswith("www."):
        hosts.append(host[4:])
    else:
        hosts.append(f"www.{host}")
    variants: list[str] = []
    for variant_host in hosts:
        for scheme in (parsed.scheme, "https", "http"):
            value = urlunparse((scheme, variant_host, path, "", parsed.query, ""))
            if value not in variants:
                variants.append(value)
        if path != "/":
            root = urlunparse(("https", variant_host, "/", "", "", ""))
            if root not in variants:
                variants.append(root)
    return variants


class CommonCrawlClient:
    """Small public-client boundary for timestamped CDX captures and WARC range reads."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        index_url: str = COMMON_CRAWL_INDEX,
        data_url: str = COMMON_CRAWL_DATA,
        timeout_seconds: float = 30.0,
        user_agent: str = "trading-prediction-lab/0.1 historical-evidence-research",
        retries: int = 4,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        self.index_url = index_url.rstrip("/")
        self.data_url = data_url.rstrip("/")
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self._headers = {"User-Agent": user_agent}
        self._collections: list[dict[str, Any]] | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> CommonCrawlClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        last_response: httpx.Response | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.get(
                    url, params=cast(dict[str, str | int] | None, params), headers=headers
                )
                last_response = response
                if response.status_code != 429 and response.status_code < 500:
                    return response
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt + 1 < self.retries:
                time.sleep(self.retry_backoff_seconds * (2**attempt))

        if last_response is not None:
            return last_response
        raise HistoricalEvidenceError(f"Common Crawl request failed: {last_error}")

    def collections(self) -> list[dict[str, Any]]:
        if self._collections is not None:
            return self._collections
        response = self._get(
            f"{self.index_url}/collinfo.json",
            headers=self._headers,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise HistoricalEvidenceError("Common Crawl collection index must be a list")
        self._collections = [item for item in payload if isinstance(item, dict) and item.get("id")]
        return self._collections

    def _eligible_collections(
        self,
        cutoff: pd.Timestamp,
        *,
        max_collections: int,
    ) -> list[dict[str, Any]]:
        eligible: list[tuple[pd.Timestamp, dict[str, Any]]] = []
        for item in self.collections():
            if not item.get("from"):
                continue
            start = _utc_timestamp(item["from"], field="crawl from")
            if start <= cutoff:
                eligible.append((start, item))
        eligible.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in eligible[:max_collections]]

    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int = 6,
    ) -> CommonCrawlCapture | None:
        cutoff_at = _utc_timestamp(cutoff, field="capture cutoff")
        candidates: list[CommonCrawlCapture] = []
        for collection in self._eligible_collections(
            cutoff_at,
            max_collections=max_collections,
        ):
            crawl_id = str(collection["id"])
            endpoint = str(collection.get("cdx-api") or f"{self.index_url}/{crawl_id}-index")
            for variant in _url_variants(url):
                response = self._get(
                    endpoint,
                    params={"url": variant, "output": "json"},
                    headers=self._headers,
                )
                if response.status_code == 404:
                    continue
                response.raise_for_status()
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
                    if capture.timestamp > cutoff_at:
                        continue
                    if capture.status != "200" or "html" not in capture.mime.lower():
                        continue
                    candidates.append(capture)
            if candidates:
                break
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.timestamp)

    def fetch_capture_text(
        self,
        capture: CommonCrawlCapture,
        *,
        max_characters: int = 12_000,
    ) -> tuple[str, str]:
        if max_characters < 500:
            raise ValueError("max_characters must be at least 500")
        start = capture.offset
        end = capture.offset + capture.length - 1
        response = self._get(
            f"{self.data_url}/{capture.filename}",
            headers={**self._headers, "Range": f"bytes={start}-{end}"},
        )
        if response.status_code not in {200, 206}:
            raise HistoricalEvidenceError(
                f"Common Crawl WARC range fetch returned HTTP {response.status_code}"
            )

        content: bytes | None = None
        try:
            for record in ArchiveIterator(io.BytesIO(response.content)):
                if record.rec_type == "response":
                    content = record.content_stream().read()
                    break
        except Exception as exc:
            raise HistoricalEvidenceError("Could not parse Common Crawl WARC record") from exc
        if not content:
            raise HistoricalEvidenceError("Common Crawl WARC record contained no response body")

        html = content.decode("utf-8", errors="replace")
        parser = _VisibleTextParser()
        parser.feed(html)
        text = parser.visible_text()
        if len(text) < 200:
            raise HistoricalEvidenceError("Archived page produced too little visible text")
        return text[:max_characters], parser.title() or capture.url


def build_commoncrawl_pilot(
    *,
    development_csv: str | Path,
    development_manifest: str | Path,
    source_markets_jsonl: str | Path,
    client: CommonCrawlClient,
    pilot_size: int = 20,
    max_reference_urls: int = 3,
    max_evidence_items: int = 2,
    max_collections: int = 6,
    max_characters_per_item: int = 12_000,
) -> tuple[dict[str, object], dict[str, object], pd.DataFrame]:
    """Construct a development-only, outcome-blind archive evidence pilot."""
    development = verify_frozen_dataset(
        csv_path=development_csv,
        manifest_path=development_manifest,
    )
    split_values = set(development.get("split", pd.Series(dtype=str)).astype(str))
    if split_values != {"development"}:
        raise HistoricalEvidenceError("Evidence pilot accepts development rows only")

    pilot = select_parent_event_pilot(development, size=pilot_size)
    markets = load_market_records(source_markets_jsonl)
    questions: dict[str, list[dict[str, object]]] = {}
    availability: dict[str, dict[str, str]] = {}
    audit_rows: list[dict[str, object]] = []
    domains: Counter[str] = Counter()

    for row in pilot.itertuples(index=False):
        question_id = str(row.question_id)
        cutoff = _utc_timestamp(row.source_cutoff_at, field="source_cutoff_at")
        market = markets.get(question_id)
        if market is None:
            raise HistoricalEvidenceError(f"Frozen source market missing question {question_id}")

        reference_urls = extract_reference_urls(market)[:max_reference_urls]
        evidence: list[EvidenceItem] = []
        seen_digests: set[str] = set()
        errors: list[str] = []
        for reference_url in reference_urls:
            if len(evidence) >= max_evidence_items:
                break
            try:
                capture = client.latest_capture_before(
                    reference_url,
                    cutoff=cutoff,
                    max_collections=max_collections,
                )
            except (HistoricalEvidenceError, httpx.HTTPError) as exc:
                errors.append(f"lookup {reference_url}: {exc}")
                continue
            if capture is None or capture.digest in seen_digests:
                continue
            try:
                text, title = client.fetch_capture_text(
                    capture,
                    max_characters=max_characters_per_item,
                )
            except (HistoricalEvidenceError, httpx.HTTPError) as exc:
                errors.append(f"fetch {reference_url}: {exc}")
                continue
            if capture.timestamp > cutoff:
                raise HistoricalEvidenceError("Common Crawl returned post-cutoff evidence")

            seen_digests.add(capture.digest)
            domains[urlparse(capture.url).netloc.lower()] += 1
            source_id = f"cc:{capture.crawl_id}:{capture.digest}"
            evidence.append(
                EvidenceItem.create(
                    source_id=source_id,
                    source_type="common-crawl-warc",
                    uri_or_reference=(
                        f"commoncrawl://{capture.crawl_id}/{capture.filename}"
                        f"#{capture.offset}:{capture.length}"
                    ),
                    title=title,
                    available_at=capture.timestamp.isoformat(),
                    retrieved_at=datetime.now(UTC).isoformat(),
                    text=text,
                )
            )

        questions[question_id] = [item.to_dict() for item in evidence]
        availability[question_id] = {
            "status": "retrieval_failure"
            if errors
            else "verified_complete"
            if evidence
            else "verified_empty",
            "detail": " | ".join(errors) if errors else "Declared bounded acquisition completed",
        }
        latest_capture = max(
            (item.available_at for item in evidence),
            default=None,
        )
        age_hours = (
            (cutoff.to_pydatetime() - latest_capture).total_seconds() / 3600.0
            if latest_capture is not None
            else None
        )
        forecasted_at = _utc_timestamp(
            row.forecasted_at,
            field="forecasted_at",
        ).isoformat()
        audit_rows.append(
            {
                "question_id": question_id,
                "question_text": str(row.question_text),
                "forecasted_at": forecasted_at,
                "event_id": str(row.event_id),
                "reference_url_count": len(reference_urls),
                "evidence_item_count": len(evidence),
                "latest_evidence_age_hours": age_hours,
                "errors": " | ".join(errors),
            }
        )

    audit = pd.DataFrame(audit_rows)
    covered = int((audit["evidence_item_count"] > 0).sum())
    with_urls = int((audit["reference_url_count"] > 0).sum())
    ages = pd.to_numeric(
        audit["latest_evidence_age_hours"],
        errors="coerce",
    ).dropna()
    summary: dict[str, object] = {
        "schema_version": 1,
        "pilot_size": len(audit),
        "parent_events": int(audit["event_id"].nunique()),
        "questions_with_reference_urls": with_urls,
        "questions_with_archived_evidence": covered,
        "coverage_rate": covered / len(audit) if len(audit) else 0.0,
        "total_evidence_items": int(audit["evidence_item_count"].sum()),
        "zero_evidence_question_ids": audit.loc[
            audit["evidence_item_count"] == 0,
            "question_id",
        ]
        .astype(str)
        .tolist(),
        "source_domains": dict(sorted(domains.items())),
        "latest_evidence_age_hours": {
            "min": float(ages.min()) if not ages.empty else None,
            "median": float(ages.median()) if not ages.empty else None,
            "max": float(ages.max()) if not ages.empty else None,
        },
        "selection_policy": (
            "time-spread first representative from each parent event; selection uses only "
            "question_id, question_text, forecasted_at, source_cutoff_at, event_id; "
            "outcomes and market probabilities are not consulted"
        ),
    }
    fixture: dict[str, object] = {
        "schema_version": 2,
        "questions": questions,
        "availability": availability,
    }
    return fixture, summary, audit
