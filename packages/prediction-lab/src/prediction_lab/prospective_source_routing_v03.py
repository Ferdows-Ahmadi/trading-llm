"""Paired baseline/RSS and resolution-aware evidence capture for prospective v0.3."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from defusedxml import ElementTree

from prediction_lab import prospective_live_enriched_v02 as enriched
from prediction_lab import prospective_live_rss_v01 as rss

METHOD_VERSION = "prospective-source-routing-v0.3"
CAPTURE_WINDOW_SECONDS = 15 * 60
MAX_RSS_ITEMS = 5
MAX_DIRECT_SOURCES = 2
SOURCE_RETRIES = 2
SOURCE_TIMEOUT_SECONDS = 20.0
SOURCE_MAX_BYTES = 2 * 1024 * 1024
SOURCE_MAX_CHARS = 12_000
SOURCE_MIN_CHARS = 100
MAX_REDIRECTS = 3
USER_AGENT = "trading-prediction-lab/0.3 prospective-source-routing"

_WS_RE = re.compile(r"\s+")
_ACCEPTED_EXACT_TYPES = {
    "text/html",
    "text/plain",
    "application/json",
    "application/xml",
    "text/xml",
}
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class SourceRoutingError(RuntimeError):
    """Raised when paired prospective evidence cannot be frozen safely."""


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


def _is_textual_content_type(content_type: str) -> bool:
    lowered = content_type.lower().split(";", 1)[0].strip()
    return (
        lowered in _ACCEPTED_EXACT_TYPES
        or lowered.endswith("+json")
        or lowered.endswith("+xml")
    )


def _safe_http_url(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.hostname or parsed.username or parsed.password:
        return None
    if parsed.port not in {None, 80, 443}:
        return None
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return None
    return text


def valid_resolution_urls(values: Sequence[object]) -> list[str]:
    """Return the first unique bounded public HTTP(S) locators in frozen source order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = _safe_http_url(value)
        if url is None or url in seen:
            continue
        seen.add(url)
        result.append(url)
        if len(result) >= MAX_DIRECT_SOURCES:
            break
    return result


def extract_source_text(raw: bytes, *, content_type: str, encoding: str | None) -> str:
    """Deterministically extract bounded readable text from supported source formats."""
    media_type = content_type.lower().split(";", 1)[0].strip()
    codec = encoding or "utf-8"
    decoded = raw.decode(codec, errors="replace")
    if media_type == "application/json" or media_type.endswith("+json"):
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError:
            visible = decoded
        else:
            visible = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    elif media_type in {"application/xml", "text/xml"} or media_type.endswith("+xml"):
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError:
            visible = decoded
        else:
            visible = " ".join(part for part in root.itertext() if part and part.strip())
    elif media_type == "text/html":
        visible = enriched.extract_visible_text(
            raw,
            content_type="text/html",
            encoding=encoding,
        )
    else:
        visible = decoded
    return _WS_RE.sub(" ", visible).strip()[:SOURCE_MAX_CHARS]


class ResolutionSourceClient:
    """Bounded direct resolver for contract-provided resolution-source locators."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        retries: int = SOURCE_RETRIES,
        timeout_seconds: float = SOURCE_TIMEOUT_SECONDS,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        self.retries = retries
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> ResolutionSourceClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request_once(self, url: str) -> tuple[httpx.Response | None, dict[str, Any]]:
        current = url
        redirects: list[str] = []
        for _ in range(MAX_REDIRECTS + 1):
            safe = _safe_http_url(current)
            if safe is None:
                return None, {"status": "unsafe_url", "url": current, "redirects": redirects}
            try:
                response = self._client.get(safe)
            except httpx.HTTPError as exc:
                return None, {"status": "transport_failure", "error": str(exc)[:500]}
            if response.status_code in _REDIRECT_CODES:
                location = response.headers.get("location")
                if not location:
                    return None, {
                        "status": "redirect_without_location",
                        "status_code": response.status_code,
                        "url": safe,
                        "redirects": redirects,
                    }
                current = urljoin(safe, location)
                redirects.append(current)
                continue
            return response, {"url": safe, "redirects": redirects}
        return None, {"status": "too_many_redirects", "redirects": redirects}

    def fetch(self, url: str) -> tuple[bytes | None, dict[str, Any]]:
        last_receipt: dict[str, Any] = {"status": "not_attempted"}
        for attempt in range(1, self.retries + 1):
            response, receipt = self._request_once(url)
            receipt["attempt"] = attempt
            if response is None:
                last_receipt = receipt
            else:
                media_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                receipt.update(
                    {
                        "status_code": response.status_code,
                        "final_url": str(response.url),
                        "content_type": media_type,
                        "encoding": response.encoding,
                    }
                )
                if response.status_code == 200:
                    declared_length = response.headers.get("content-length")
                    if declared_length:
                        try:
                            if int(declared_length) > SOURCE_MAX_BYTES:
                                receipt["status"] = "oversized"
                                return None, receipt
                        except ValueError:
                            pass
                    raw = response.content
                    receipt["raw_bytes"] = len(raw)
                    if len(raw) > SOURCE_MAX_BYTES:
                        receipt["status"] = "oversized"
                        return None, receipt
                    if not _is_textual_content_type(media_type):
                        receipt["status"] = "non_text"
                        return None, receipt
                    receipt["status"] = "retrieved"
                    return raw, receipt
                if response.status_code != 429 and response.status_code < 500:
                    receipt["status"] = "non_success"
                    return None, receipt
                receipt["status"] = "transient_http"
                last_receipt = receipt
            if attempt < self.retries:
                time.sleep(1.0 * (2 ** (attempt - 1)))
        return None, last_receipt


def capture_paired_evidence(
    *,
    question_id: str,
    question_text: str,
    resolution_sources: Sequence[object],
    output_directory: Path,
    rss_client: rss.GoogleNewsRssClient,
    source_client: ResolutionSourceClient,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Freeze Condition A RSS and Condition B RSS+resolution-source evidence together."""
    now = clock or (lambda: datetime.now(UTC))
    row_directory = output_directory / _safe_name(question_id)
    if row_directory.exists():
        raise SourceRoutingError(f"Refusing to replace existing v0.3 capture: {question_id}")
    row_directory.mkdir(parents=True)

    started = now()
    raw_rss: bytes | None = None
    request_url: str | None = None
    error: str | None = None
    baseline_items: list[dict[str, Any]] = []
    routed_items: list[dict[str, Any]] = []
    source_receipts: list[dict[str, Any]] = []
    valid_urls = valid_resolution_urls(resolution_sources)

    try:
        raw_rss, request_url = rss_client.search(question_text)
        (row_directory / "raw-google-news-rss.xml").write_bytes(raw_rss)
        parsed_items = rss.parse_rss_items(raw_rss, max_items=MAX_RSS_ITEMS)

        for index, url in enumerate(valid_urls, start=1):
            raw_source, receipt = source_client.fetch(url)
            source_receipt = {
                "source_index": index,
                "locator": url,
                **receipt,
                "admitted": False,
            }
            if raw_source is not None:
                raw_dir = row_directory / "raw-resolution-sources"
                raw_dir.mkdir(parents=True, exist_ok=True)
                raw_path = raw_dir / f"source-{index:02d}.bin"
                raw_path.write_bytes(raw_source)
                source_receipt["raw_sha256"] = _sha256(raw_source)
                text = extract_source_text(
                    raw_source,
                    content_type=str(receipt.get("content_type") or "text/plain"),
                    encoding=(
                        str(receipt["encoding"])
                        if receipt.get("encoding") is not None
                        else None
                    ),
                )
                source_receipt["visible_chars"] = len(text)
                if len(text) >= SOURCE_MIN_CHARS:
                    routed_items.append(
                        {
                            "source_id": "resolution-source:"
                            + hashlib.sha256(url.encode("utf-8")).hexdigest(),
                            "source_type": "contract-resolution-source",
                            "uri_or_reference": str(receipt.get("final_url") or url),
                            "title": f"Contract resolution source {index}: {urlparse(url).hostname}",
                            "published_at": "",
                            "available_at": "PENDING",
                            "text": text,
                        }
                    )
                    source_receipt["admitted"] = True
                else:
                    source_receipt["status"] = "too_short"
            source_receipts.append(source_receipt)

        completed = now()
        elapsed = (completed - started).total_seconds()
        if elapsed < 0 or elapsed > CAPTURE_WINDOW_SECONDS:
            raise SourceRoutingError(
                f"Evidence capture exceeded frozen {CAPTURE_WINDOW_SECONDS}s window"
            )
        completed_at = _iso_z(completed)
        baseline_items = [item.to_dict(available_at=completed_at) for item in parsed_items]
        for item in routed_items:
            item["available_at"] = completed_at
        condition_b_items = [*baseline_items, *routed_items]
        status = "verified_complete" if baseline_items else "verified_empty"
    except (rss.LiveCaptureError, SourceRoutingError, httpx.HTTPError) as exc:
        completed = now()
        elapsed = (completed - started).total_seconds()
        completed_at = _iso_z(completed)
        status = "retrieval_failure"
        error = str(exc)[:500]
        baseline_items = []
        condition_b_items = []
        routed_items = []

    condition_a_bytes = _canonical_bytes(baseline_items)
    condition_b_bytes = _canonical_bytes(condition_b_items)
    receipts_bytes = _canonical_bytes(source_receipts)
    (row_directory / "condition-a-evidence.json").write_bytes(condition_a_bytes)
    (row_directory / "condition-b-evidence.json").write_bytes(condition_b_bytes)
    (row_directory / "resolution-source-receipts.json").write_bytes(receipts_bytes)

    manifest: dict[str, object] = {
        "schema_version": 1,
        "method_version": METHOD_VERSION,
        "question_id": question_id,
        "question_text_sha256": _sha256(question_text.encode("utf-8")),
        "capture_started_at": _iso_z(started),
        "capture_completed_at": completed_at,
        "capture_elapsed_seconds": elapsed,
        "capture_window_seconds": CAPTURE_WINDOW_SECONDS,
        "provider": "google-news-rss-plus-contract-resolution-source",
        "request_url": request_url,
        "raw_rss_sha256": _sha256(raw_rss) if raw_rss is not None else None,
        "resolution_source_locators": [str(value) for value in resolution_sources],
        "valid_resolution_urls": valid_urls,
        "direct_source_attempts": len(source_receipts),
        "direct_source_successes": sum(1 for value in source_receipts if value.get("admitted")),
        "condition_a_evidence_items": len(baseline_items),
        "condition_b_evidence_items": len(condition_b_items),
        "condition_a_sha256": _sha256(condition_a_bytes),
        "condition_b_sha256": _sha256(condition_b_bytes),
        "source_receipts_sha256": _sha256(receipts_bytes),
        "status": status,
        "error": error,
        "market_snapshot_bound": False,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    (row_directory / "capture-manifest.json").write_bytes(_canonical_bytes(manifest))
    return manifest
