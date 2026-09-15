"""Prospective live RSS evidence capture for the v0.1 local pilot."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import httpx

METHOD_VERSION = "prospective-live-rss-v0.1"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
CAPTURE_WINDOW_SECONDS = 15 * 60
MAX_EVIDENCE_ITEMS = 5
RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
USER_AGENT = "trading-prediction-lab/0.1 prospective-live-pilot"

_TAG_RE = re.compile(r"<[^>]+>")


class LiveCaptureError(RuntimeError):
    """Raised when a prospective live capture cannot be frozen safely."""


@dataclass(frozen=True)
class RssEvidenceItem:
    title: str
    link: str
    source: str
    published_at: str
    description: str

    def to_dict(self, *, available_at: str) -> dict[str, str]:
        text_parts = [self.title]
        if self.description:
            text_parts.append(self.description)
        if self.source:
            text_parts.append(f"Source: {self.source}")
        return {
            "source_id": "google-news-rss:"
            + hashlib.sha256(self.link.encode("utf-8")).hexdigest(),
            "source_type": "live-google-news-rss",
            "uri_or_reference": self.link,
            "title": self.title,
            "published_at": self.published_at,
            "available_at": available_at,
            "text": "\n\n".join(text_parts),
        }


def _iso_z(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise LiveCaptureError(f"Invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_question_name(question_id: str) -> str:
    return hashlib.sha256(question_id.encode("utf-8")).hexdigest()


def _clean_html(value: str | None) -> str:
    if not value:
        return ""
    without_tags = _TAG_RE.sub(" ", value)
    return " ".join(html.unescape(without_tags).split())


class GoogleNewsRssClient:
    """Small live-only discovery client. Raw RSS is frozen before parsing."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = GOOGLE_NEWS_RSS_URL,
        retries: int = RETRIES,
        retry_backoff_seconds: float = RETRY_BACKOFF_SECONDS,
        timeout_seconds: float = 30.0,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        self.endpoint = endpoint
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GoogleNewsRssClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def search(self, question_text: str) -> tuple[bytes, str]:
        query = question_text.strip()
        if not query:
            raise LiveCaptureError("question_text cannot be empty")
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.get(
                    self.endpoint,
                    params={
                        "q": query,
                        "hl": "en-US",
                        "gl": "US",
                        "ceid": "US:en",
                    },
                    headers={"User-Agent": USER_AGENT},
                )
                if response.status_code == 200:
                    return response.content, str(response.request.url)
                if response.status_code != 429 and response.status_code < 500:
                    raise LiveCaptureError(
                        f"Google News RSS returned HTTP {response.status_code}"
                    )
                last_error = LiveCaptureError(
                    f"Google News RSS transient HTTP {response.status_code}"
                )
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt + 1 < self.retries and self.retry_backoff_seconds > 0:
                time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise LiveCaptureError(f"Google News RSS request failed: {last_error}")


def parse_rss_items(
    raw_xml: bytes,
    *,
    max_items: int = MAX_EVIDENCE_ITEMS,
) -> list[RssEvidenceItem]:
    if max_items < 1:
        raise ValueError("max_items must be at least 1")
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise LiveCaptureError("Google News RSS returned malformed XML") from exc

    items: list[RssEvidenceItem] = []
    seen_links: set[str] = set()
    for node in root.findall("./channel/item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not title or not link or link in seen_links:
            continue
        seen_links.add(link)
        source_node = node.find("source")
        source = (
            source_node.text.strip()
            if source_node is not None and source_node.text
            else ""
        )
        items.append(
            RssEvidenceItem(
                title=title,
                link=link,
                source=source,
                published_at=(node.findtext("pubDate") or "").strip(),
                description=_clean_html(node.findtext("description")),
            )
        )
        if len(items) >= max_items:
            break
    return items


def capture_question(
    *,
    question_id: str,
    question_text: str,
    output_directory: Path,
    client: GoogleNewsRssClient,
    clock: Callable[[], datetime] | None = None,
    max_items: int = MAX_EVIDENCE_ITEMS,
) -> dict[str, object]:
    """Capture one row. A successful zero-result response is verified_empty."""
    now = clock or (lambda: datetime.now(UTC))
    row_directory = output_directory / _safe_question_name(question_id)
    if row_directory.exists():
        raise LiveCaptureError(f"Refusing to replace existing live capture: {question_id}")
    row_directory.mkdir(parents=True)

    capture_started = now()
    raw_xml: bytes | None = None
    request_url: str | None = None
    error: str | None = None
    items: list[RssEvidenceItem] = []

    try:
        raw_xml, request_url = client.search(question_text)
        capture_completed = now()
        elapsed = (capture_completed - capture_started).total_seconds()
        if elapsed < 0 or elapsed > CAPTURE_WINDOW_SECONDS:
            raise LiveCaptureError(
                f"Evidence capture exceeded frozen {CAPTURE_WINDOW_SECONDS}s window"
            )
        raw_path = row_directory / "raw-google-news-rss.xml"
        raw_path.write_bytes(raw_xml)
        items = parse_rss_items(raw_xml, max_items=max_items)
        status = "verified_complete" if items else "verified_empty"
    except (LiveCaptureError, httpx.HTTPError) as exc:
        capture_completed = now()
        elapsed = (capture_completed - capture_started).total_seconds()
        status = "retrieval_failure"
        error = str(exc)[:500]

    completed_at = _iso_z(capture_completed)
    evidence = [item.to_dict(available_at=completed_at) for item in items]
    evidence_payload = _canonical_json_bytes(evidence)
    (row_directory / "evidence.json").write_bytes(evidence_payload)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "method_version": METHOD_VERSION,
        "question_id": question_id,
        "question_text_sha256": _sha256_bytes(question_text.encode("utf-8")),
        "capture_started_at": _iso_z(capture_started),
        "capture_completed_at": completed_at,
        "capture_elapsed_seconds": elapsed,
        "capture_window_seconds": CAPTURE_WINDOW_SECONDS,
        "provider": "google-news-rss",
        "request_url": request_url,
        "raw_response_sha256": _sha256_bytes(raw_xml) if raw_xml is not None else None,
        "evidence_sha256": _sha256_bytes(evidence_payload),
        "status": status,
        "evidence_items": len(evidence),
        "error": error,
        "market_snapshot_bound": False,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    (row_directory / "capture-manifest.json").write_bytes(
        _canonical_json_bytes(manifest)
    )
    return manifest


def bind_market_snapshot(
    manifest: dict[str, object],
    *,
    market_price_timestamp: str,
) -> dict[str, object]:
    """Bind a later market snapshot without allowing evidence newer than the comparator."""
    if manifest.get("status") not in {"verified_complete", "verified_empty"}:
        raise LiveCaptureError("Cannot bind a market snapshot to non-terminal evidence")
    started = _parse_timestamp(str(manifest["capture_started_at"]))
    completed = _parse_timestamp(str(manifest["capture_completed_at"]))
    market_at = _parse_timestamp(market_price_timestamp)
    if market_at < completed:
        raise LiveCaptureError("Market snapshot predates completed evidence capture")
    if (market_at - started).total_seconds() > CAPTURE_WINDOW_SECONDS:
        raise LiveCaptureError("Market snapshot falls outside frozen capture window")
    bound = dict(manifest)
    bound["market_price_timestamp"] = _iso_z(market_at)
    bound["market_snapshot_bound"] = True
    return bound


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question_id")
    parser.add_argument("question_text")
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--max-items", type=int, default=MAX_EVIDENCE_ITEMS)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    with GoogleNewsRssClient() as client:
        manifest = capture_question(
            question_id=args.question_id,
            question_text=args.question_text,
            output_directory=args.output_directory,
            client=client,
            max_items=args.max_items,
        )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    if manifest["status"] == "retrieval_failure":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
