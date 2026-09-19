"""Prospective Google News RSS capture with bounded optional article enrichment."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

from prediction_lab import prospective_live_rss_v01 as rss

METHOD_VERSION = "prospective-live-enriched-v0.2"
CAPTURE_WINDOW_SECONDS = 15 * 60
MAX_RSS_ITEMS = 5
MAX_ENRICH_ITEMS = 3
ARTICLE_RETRIES = 2
ARTICLE_TIMEOUT_SECONDS = 20.0
ARTICLE_MAX_BYTES = 2 * 1024 * 1024
ARTICLE_MAX_CHARS = 8_000
ARTICLE_MIN_CHARS = 200
USER_AGENT = "trading-prediction-lab/0.2 prospective-live-multimodel"

_WS_RE = re.compile(r"\s+")


class EnrichedCaptureError(RuntimeError):
    """Raised when the baseline RSS capture cannot be frozen safely."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _iso_z(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_name(question_id: str) -> str:
    return hashlib.sha256(question_id.encode("utf-8")).hexdigest()


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self.parts.append(data)


def extract_visible_text(raw: bytes, *, content_type: str, encoding: str | None) -> str:
    codec = encoding or "utf-8"
    text = raw.decode(codec, errors="replace")
    if content_type.lower().startswith("text/plain"):
        visible = text
    else:
        parser = _VisibleTextParser()
        parser.feed(text)
        visible = " ".join(parser.parts)
    return _WS_RE.sub(" ", visible).strip()[:ARTICLE_MAX_CHARS]


class ArticleEnricher:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        retries: int = ARTICLE_RETRIES,
        timeout_seconds: float = ARTICLE_TIMEOUT_SECONDS,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        self.retries = retries
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ArticleEnricher:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def fetch(self, url: str) -> tuple[bytes | None, dict[str, Any]]:
        last_error = "unknown"
        for attempt in range(1, self.retries + 1):
            try:
                response = self._client.get(url)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                receipt: dict[str, Any] = {
                    "attempt": attempt,
                    "status_code": response.status_code,
                    "final_url": str(response.url),
                    "content_type": content_type,
                    "encoding": response.encoding,
                }
                if response.status_code == 200:
                    raw = response.content
                    receipt["raw_bytes"] = len(raw)
                    if len(raw) > ARTICLE_MAX_BYTES:
                        receipt["status"] = "oversized"
                        return None, receipt
                    if content_type not in {"text/html", "text/plain"}:
                        receipt["status"] = "non_text"
                        return None, receipt
                    receipt["status"] = "retrieved"
                    return raw, receipt
                if response.status_code != 429 and response.status_code < 500:
                    receipt["status"] = "non_success"
                    return None, receipt
                last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            if attempt < self.retries:
                time.sleep(1.0 * (2 ** (attempt - 1)))
        return None, {"status": "transport_failure", "error": last_error[:500]}


def capture_question(
    *,
    question_id: str,
    question_text: str,
    output_directory: Path,
    rss_client: rss.GoogleNewsRssClient,
    article_client: ArticleEnricher,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    now = clock or (lambda: datetime.now(UTC))
    row_directory = output_directory / _safe_name(question_id)
    if row_directory.exists():
        raise EnrichedCaptureError(f"Refusing to replace existing capture: {question_id}")
    row_directory.mkdir(parents=True)

    started = now()
    raw_rss: bytes | None = None
    request_url: str | None = None
    error: str | None = None
    final_items: list[dict[str, Any]] = []
    enrichment_receipts: list[dict[str, Any]] = []

    try:
        raw_rss, request_url = rss_client.search(question_text)
        (row_directory / "raw-google-news-rss.xml").write_bytes(raw_rss)
        items = rss.parse_rss_items(raw_rss, max_items=MAX_RSS_ITEMS)

        for index, item in enumerate(items):
            base_item = item.to_dict(available_at=_iso_z(started))
            text = str(base_item["text"])
            enrichment: dict[str, Any] = {
                "item_index": index,
                "source_id": base_item["source_id"],
                "attempted": index < MAX_ENRICH_ITEMS,
                "enriched": False,
            }
            if index < MAX_ENRICH_ITEMS:
                raw_article, receipt = article_client.fetch(item.link)
                enrichment.update(receipt)
                if raw_article is not None:
                    article_dir = row_directory / "raw-articles"
                    article_dir.mkdir(parents=True, exist_ok=True)
                    article_path = article_dir / f"article-{index + 1:02d}.bin"
                    article_path.write_bytes(raw_article)
                    enrichment["raw_sha256"] = _sha256(raw_article)
                    visible = extract_visible_text(
                        raw_article,
                        content_type=str(receipt.get("content_type") or "text/html"),
                        encoding=(
                            str(receipt["encoding"])
                            if receipt.get("encoding") is not None
                            else None
                        ),
                    )
                    enrichment["visible_chars"] = len(visible)
                    if len(visible) >= ARTICLE_MIN_CHARS:
                        text = (
                            f"{item.title}\nSource: {item.source}\n"
                            f"Full article text:\n{visible}"
                        )
                        enrichment["enriched"] = True
                    else:
                        enrichment["status"] = "too_short"
            enriched_item = dict(base_item)
            enriched_item["text"] = text
            enriched_item["enrichment"] = enrichment
            final_items.append(enriched_item)
            enrichment_receipts.append(enrichment)

        completed = now()
        elapsed = (completed - started).total_seconds()
        if elapsed < 0 or elapsed > CAPTURE_WINDOW_SECONDS:
            raise EnrichedCaptureError(
                f"Evidence capture exceeded frozen {CAPTURE_WINDOW_SECONDS}s window"
            )
        completed_at = _iso_z(completed)
        for item in final_items:
            item["available_at"] = completed_at
        status = "verified_complete" if final_items else "verified_empty"
    except (rss.LiveCaptureError, EnrichedCaptureError, httpx.HTTPError) as exc:
        completed = now()
        elapsed = (completed - started).total_seconds()
        completed_at = _iso_z(completed)
        status = "retrieval_failure"
        error = str(exc)[:500]
        final_items = []

    evidence_bytes = _canonical_bytes(final_items)
    (row_directory / "evidence.json").write_bytes(evidence_bytes)
    (row_directory / "enrichment-receipts.json").write_bytes(
        _canonical_bytes(enrichment_receipts)
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "method_version": METHOD_VERSION,
        "question_id": question_id,
        "question_text_sha256": _sha256(question_text.encode("utf-8")),
        "capture_started_at": _iso_z(started),
        "capture_completed_at": completed_at,
        "capture_elapsed_seconds": elapsed,
        "capture_window_seconds": CAPTURE_WINDOW_SECONDS,
        "provider": "google-news-rss-plus-bounded-direct-enrichment",
        "request_url": request_url,
        "raw_rss_sha256": _sha256(raw_rss) if raw_rss is not None else None,
        "evidence_sha256": _sha256(evidence_bytes),
        "status": status,
        "evidence_items": len(final_items),
        "enrichment_attempts": sum(1 for r in enrichment_receipts if r.get("attempted")),
        "enrichment_successes": sum(1 for r in enrichment_receipts if r.get("enriched")),
        "error": error,
        "market_snapshot_bound": False,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    (row_directory / "capture-manifest.json").write_bytes(_canonical_bytes(manifest))
    return manifest
