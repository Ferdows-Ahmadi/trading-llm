"""Expand frozen historical-contract source discovery without changing candidate membership."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import pandas as pd
from warcio.archiveiterator import ArchiveIterator  # type: ignore[import-untyped]

from prediction_lab.capture_index_client import (
    CaptureIndexCommonCrawlClient,
    CommonCrawlTransportError,
    canonical_index_key,
)
from prediction_lab.commoncrawl_evidence import (
    CommonCrawlCapture,
    HistoricalEvidenceError,
    _utc_timestamp,
)
from prediction_lab.historical_validity_sources import (
    HistoricalSourceError,
    SourceTransportError,
    WaybackAuditCdxClient,
)
from prediction_lab.research_types import ResearchContractError, canonical_json_bytes
from prediction_lab.wayback_content import WaybackReplayClient, extract_archived_html_text

CANDIDATE_SHA256 = "6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21"
CANDIDATE_ROWS = 64
V1_ARTIFACT_DIGEST = (
    "sha256:fa1b454d5a44699f7f314db5871268d416856db369bc6e58c2c54d8b79047622"
)
V2_PROTOCOL_COMMIT = "97ac0e7ee15c0b315a6369a4a955f5f3b078ed57"
V2_CLARIFICATION_COMMIT = "063a86e3b457ef17e72db49b4467e49445933866"
COMMON_CRAWL_MAX_COLLECTIONS = 6

_ALLOWED_CANDIDATE_COLUMNS = (
    "question_id",
    "question_text",
    "forecasted_at",
    "source_cutoff_at",
    "event_id",
    "category",
)
_FORBIDDEN_LOCATOR_KEYS = {
    "outcomePrices",
    "volume",
    "volumeNum",
    "bestBid",
    "bestAsk",
    "lastTradePrice",
}
_SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class HistoricalSourceV2Error(ResearchContractError):
    """Raised when source-discovery v2 violates its frozen acquisition contract."""


@dataclass(frozen=True)
class V2Capture:
    provider: str
    timestamp: pd.Timestamp
    requested_url: str
    captured_url: str
    mime: str
    status: str
    identity: str
    replay_reference: str
    provider_record: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


class CaptureProvider(Protocol):
    provider_name: str

    def latest_capture_before(self, url: str, *, cutoff: object) -> V2Capture | None: ...

    def freeze_body(self, capture: V2Capture) -> bytes: ...


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return " ".join(text.split()).strip()


def _safe_text_hash(value: object) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    return _sha256(normalized.encode("utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HistoricalSourceV2Error(
                f"Malformed JSONL at {path.name}:{line_number}"
            ) from exc
        if not isinstance(payload, dict):
            raise HistoricalSourceV2Error(
                f"JSONL row is not an object at {path.name}:{line_number}"
            )
        rows.append(payload)
    return rows


def _recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        result = set(value)
        for child in value.values():
            result |= _recursive_keys(child)
        return result
    if isinstance(value, list):
        result: set[str] = set()
        for child in value:
            result |= _recursive_keys(child)
        return result
    return set()


def load_v1_locators(path: Path, *, expected_rows: int = CANDIDATE_ROWS) -> dict[str, dict[str, Any]]:
    rows = _load_jsonl(path)
    if len(rows) != expected_rows:
        raise HistoricalSourceV2Error("V1 locator ledger row count changed")
    by_question: dict[str, dict[str, Any]] = {}
    for row in rows:
        question_id = str(row.get("question_id") or "").strip()
        if not question_id or question_id in by_question:
            raise HistoricalSourceV2Error("V1 locator ledger IDs are missing or duplicated")
        if row.get("locator_status") != "success" or not isinstance(row.get("locator"), dict):
            raise HistoricalSourceV2Error("V2 requires a successful frozen V1 locator per candidate")
        locator = row["locator"]
        leaked = _FORBIDDEN_LOCATOR_KEYS & _recursive_keys(locator)
        if leaked:
            raise HistoricalSourceV2Error(
                "V1 locator contains forbidden price/outcome metadata: " + ", ".join(sorted(leaked))
            )
        by_question[question_id] = row
    return by_question


def _validated_slug(value: object) -> str | None:
    slug = str(value or "").strip()
    if not slug:
        return None
    if not _SAFE_SLUG.fullmatch(slug):
        raise HistoricalSourceV2Error(f"Unsafe frozen locator slug: {slug!r}")
    return slug


def derive_v2_urls(locator: dict[str, Any]) -> list[tuple[str, str]]:
    market = locator.get("market")
    if not isinstance(market, dict):
        raise HistoricalSourceV2Error("Frozen V1 locator has no market object")
    market_slug = _validated_slug(market.get("slug"))
    patterns: list[tuple[str, str]] = []
    if market_slug:
        patterns.extend(
            [
                ("market-page:market-slug", f"https://polymarket.com/market/{market_slug}"),
                ("event-page:market-slug", f"https://polymarket.com/event/{market_slug}"),
                (
                    "gamma-market-slug",
                    f"https://gamma-api.polymarket.com/markets/slug/{market_slug}",
                ),
            ]
        )

    events = locator.get("events")
    if isinstance(events, list):
        event_slugs = sorted(
            {
                slug
                for item in events
                if isinstance(item, dict)
                for slug in [_validated_slug(item.get("slug"))]
                if slug
            }
        )
        for slug in event_slugs:
            patterns.extend(
                [
                    (f"event-page:event-slug:{slug}", f"https://polymarket.com/event/{slug}"),
                    (
                        f"gamma-event-slug:{slug}",
                        f"https://gamma-api.polymarket.com/events/slug/{slug}",
                    ),
                ]
            )

    deduplicated: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pattern, url in patterns:
        if url not in seen:
            seen.add(url)
            deduplicated.append((pattern, url))
    return deduplicated


def _same_logical_url(requested_url: str, captured_url: str) -> bool:
    try:
        requested = urlparse(requested_url)
        captured = urlparse(captured_url)
    except ValueError:
        return False

    def host(value: str) -> str:
        lowered = value.lower()
        return lowered[4:] if lowered.startswith("www.") else lowered

    return (
        host(requested.netloc) == host(captured.netloc)
        and (requested.path or "/") == (captured.path or "/")
        and requested.query == captured.query
    )


class WaybackV2Provider:
    provider_name = "wayback"

    def __init__(
        self,
        *,
        cdx: WaybackAuditCdxClient | None = None,
        replay: WaybackReplayClient | None = None,
    ) -> None:
        self.cdx = cdx or WaybackAuditCdxClient(minimum_interval_seconds=0.75)
        self.replay = replay or WaybackReplayClient(minimum_interval_seconds=0.5)
        self._owns_cdx = cdx is None
        self._owns_replay = replay is None

    def close(self) -> None:
        if self._owns_cdx:
            self.cdx.close()
        if self._owns_replay:
            self.replay.close()

    def __enter__(self) -> WaybackV2Provider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def latest_capture_before(self, url: str, *, cutoff: object) -> V2Capture | None:
        capture = self.cdx.latest_capture_before(url, cutoff=cutoff)
        if capture is None:
            return None
        return V2Capture(
            provider=self.provider_name,
            timestamp=capture.timestamp,
            requested_url=url,
            captured_url=capture.original,
            mime=capture.mime,
            status=capture.status,
            identity=capture.digest,
            replay_reference=capture.replay_url,
            provider_record=capture.to_dict(),
        )

    def freeze_body(self, capture: V2Capture) -> bytes:
        response = self.replay.fetch(capture.replay_reference)
        if not response.content:
            raise HistoricalSourceV2Error("Wayback replay body is empty")
        return response.content


class CommonCrawlV2Provider(CaptureIndexCommonCrawlClient):
    provider_name = "common-crawl"

    def collections_manifest(self) -> tuple[list[dict[str, Any]], str]:
        payload = self.collections()
        digest = _sha256(canonical_json_bytes(payload))
        return payload, digest

    def latest_capture_before(self, url: str, *, cutoff: object) -> V2Capture | None:
        cutoff_at = _utc_timestamp(cutoff, field="capture cutoff")
        index_key = canonical_index_key(url)
        transport_errors: list[str] = []
        collections = self._eligible_collections(
            cutoff_at,
            max_collections=COMMON_CRAWL_MAX_COLLECTIONS,
        )
        for collection in collections:
            crawl_id = str(collection["id"])
            endpoint = str(
                collection.get("cdx-api") or f"{self.index_url}/{crawl_id}-index"
            )
            try:
                response = self._get(
                    endpoint,
                    params={"url": index_key, "output": "json", "matchType": "exact"},
                    headers=self._headers,
                )
            except CommonCrawlTransportError as exc:
                transport_errors.append(f"{crawl_id}: {exc}")
                continue
            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                transport_errors.append(
                    f"{crawl_id}: Common Crawl index HTTP {response.status_code}"
                )
                continue

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
                if capture.timestamp > cutoff_at:
                    continue
                if not _same_logical_url(url, capture.url):
                    continue
                mime = capture.mime.lower()
                if capture.status != "200" or not ("html" in mime or "json" in mime):
                    continue
                valid.append(capture)
            if valid:
                capture = max(valid, key=lambda item: item.timestamp)
                return V2Capture(
                    provider=self.provider_name,
                    timestamp=capture.timestamp,
                    requested_url=url,
                    captured_url=capture.url,
                    mime=capture.mime,
                    status=capture.status,
                    identity=capture.digest,
                    replay_reference=(
                        f"commoncrawl://{capture.crawl_id}/{capture.filename}"
                        f"#{capture.offset}:{capture.length}"
                    ),
                    provider_record=capture.to_dict(),
                )

        if transport_errors:
            raise CommonCrawlTransportError(
                "Common Crawl lookup incomplete: " + " | ".join(transport_errors[:3])
            )
        return None

    def freeze_body(self, capture: V2Capture) -> bytes:
        record = capture.provider_record
        try:
            filename = str(record["filename"])
            offset = int(record["offset"])
            length = int(record["length"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoricalSourceV2Error("Malformed Common Crawl capture identity") from exc
        response = self._get(
            f"{self.data_url}/{filename}",
            headers={**self._headers, "Range": f"bytes={offset}-{offset + length - 1}"},
        )
        if response.status_code not in {200, 206}:
            raise SourceTransportError(
                f"Common Crawl WARC range HTTP {response.status_code}"
            )
        try:
            for warc_record in ArchiveIterator(io.BytesIO(response.content)):
                if warc_record.rec_type == "response":
                    body = warc_record.content_stream().read()
                    if body:
                        return body
        except Exception as exc:
            raise HistoricalSourceV2Error("Could not parse Common Crawl WARC record") from exc
        raise HistoricalSourceV2Error("Common Crawl WARC record contained no response body")


def _find_market_object(payload: object, market_id: str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if str(payload.get("id") or "") == market_id and payload.get("question") is not None:
            return payload
        markets = payload.get("markets")
        if isinstance(markets, list):
            for item in markets:
                found = _find_market_object(item, market_id)
                if found is not None:
                    return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_market_object(item, market_id)
            if found is not None:
                return found
    return None


def _freeze_content(
    *,
    body: bytes,
    mime: str,
    market_id: str,
    benchmark_question: str,
    provider: str,
    raw_directory: Path,
    text_directory: Path,
) -> dict[str, object]:
    if not body:
        raise HistoricalSourceV2Error("Archived body is empty")
    raw_sha = _sha256(body)
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_directory / f"{provider}-{raw_sha}.bin"
    if not raw_path.exists():
        raw_path.write_bytes(body)

    benchmark_normalized = _normalize_text(benchmark_question)
    diagnostic: dict[str, object] = {
        "raw_sha256": raw_sha,
        "raw_bytes": len(body),
        "benchmark_question_normalized_sha256": _sha256(
            benchmark_normalized.encode("utf-8")
        ),
    }
    if "json" in mime.lower():
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HistoricalSourceV2Error("Archived JSON body is not parseable") from exc
        diagnostic["canonical_json_sha256"] = _sha256(canonical_json_bytes(payload))
        historical = _find_market_object(payload, market_id)
        if historical is None:
            diagnostic["historical_market_object_found"] = False
            diagnostic["benchmark_question_exact_match"] = False
        else:
            historical_question = _normalize_text(historical.get("question") or "")
            diagnostic["historical_market_object_found"] = True
            diagnostic["historical_question_sha256"] = (
                _sha256(historical_question.encode("utf-8")) if historical_question else None
            )
            diagnostic["benchmark_question_exact_match"] = (
                historical_question == benchmark_normalized
            )
            diagnostic["historical_description_sha256"] = _safe_text_hash(
                historical.get("description") or historical.get("rules") or ""
            )
            diagnostic["historical_resolution_source"] = str(
                historical.get("resolutionSource") or ""
            ).strip()
        return diagnostic

    text = extract_archived_html_text(body.decode("utf-8", errors="replace"))
    text_sha = _sha256(text.encode("utf-8"))
    text_directory.mkdir(parents=True, exist_ok=True)
    text_path = text_directory / f"{provider}-{text_sha}.txt"
    if not text_path.exists():
        text_path.write_text(text, encoding="utf-8")
    diagnostic["text_sha256"] = text_sha
    diagnostic["text_chars"] = len(text)
    diagnostic["benchmark_question_exact_match"] = (
        benchmark_normalized in _normalize_text(text)
    )
    return diagnostic


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def discover_v2_sources(
    *,
    candidates_csv: Path,
    v1_locators_jsonl: Path,
    output_directory: Path,
    providers: list[CaptureProvider],
    code_commit: str,
    candidate_sha256: str = CANDIDATE_SHA256,
    expected_rows: int = CANDIDATE_ROWS,
    commoncrawl_collections: list[dict[str, Any]] | None = None,
    commoncrawl_collections_sha256: str | None = None,
) -> dict[str, object]:
    if _sha256(candidates_csv.read_bytes()) != candidate_sha256:
        raise HistoricalSourceV2Error("Fresh candidate CSV digest changed")
    frame = pd.read_csv(candidates_csv, dtype={"question_id": str})
    if len(frame) != expected_rows or tuple(frame.columns) != _ALLOWED_CANDIDATE_COLUMNS:
        raise HistoricalSourceV2Error("Fresh candidate artifact shape changed")
    if frame["question_id"].nunique() != expected_rows:
        raise HistoricalSourceV2Error("Fresh candidate IDs are not unique")

    locators = load_v1_locators(v1_locators_jsonl, expected_rows=expected_rows)
    if set(frame["question_id"].astype(str)) != set(locators):
        raise HistoricalSourceV2Error("Candidate IDs and V1 locator IDs differ")

    output_directory.mkdir(parents=True, exist_ok=True)
    raw_directory = output_directory / "raw"
    text_directory = output_directory / "text"
    rows: list[dict[str, object]] = []

    for candidate in frame.itertuples(index=False):
        question_id = str(candidate.question_id)
        locator = locators[question_id]["locator"]
        urls = derive_v2_urls(locator)
        if not urls:
            rows.append(
                {
                    "question_id": question_id,
                    "event_id": str(candidate.event_id),
                    "forecasted_at": str(candidate.forecasted_at),
                    "provider": None,
                    "pattern": "no-safe-slug",
                    "url": None,
                    "lookup_status": "no_url",
                    "capture": None,
                    "content": None,
                    "error": None,
                }
            )
            continue

        for pattern, url in urls:
            for provider in providers:
                record: dict[str, object] = {
                    "question_id": question_id,
                    "event_id": str(candidate.event_id),
                    "forecasted_at": str(candidate.forecasted_at),
                    "provider": provider.provider_name,
                    "pattern": pattern,
                    "url": url,
                    "lookup_status": "no_capture",
                    "capture": None,
                    "content": None,
                    "error": None,
                }
                try:
                    capture = provider.latest_capture_before(
                        url,
                        cutoff=candidate.forecasted_at,
                    )
                    if capture is not None:
                        record["capture"] = capture.to_dict()
                        try:
                            body = provider.freeze_body(capture)
                            record["content"] = _freeze_content(
                                body=body,
                                mime=capture.mime,
                                market_id=question_id,
                                benchmark_question=str(candidate.question_text),
                                provider=provider.provider_name,
                                raw_directory=raw_directory,
                                text_directory=text_directory,
                            )
                            record["lookup_status"] = "capture"
                        except (ResearchContractError, HistoricalEvidenceError, httpx.HTTPError) as exc:
                            record["lookup_status"] = "content_failure"
                            record["error"] = f"{type(exc).__name__}: {exc}"
                except (
                    ResearchContractError,
                    HistoricalEvidenceError,
                    CommonCrawlTransportError,
                    httpx.HTTPError,
                ) as exc:
                    record["lookup_status"] = "transport_failure"
                    record["error"] = f"{type(exc).__name__}: {exc}"
                rows.append(record)

    ledger_path = output_directory / "source-lookups-v2.jsonl"
    ledger_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    if commoncrawl_collections is not None:
        _atomic_json(
            output_directory / "commoncrawl-collections.json",
            commoncrawl_collections,
        )

    captures = sum(row["lookup_status"] == "capture" for row in rows)
    transport_failures = sum(row["lookup_status"] == "transport_failure" for row in rows)
    content_failures = sum(row["lookup_status"] == "content_failure" for row in rows)
    no_captures = sum(row["lookup_status"] == "no_capture" for row in rows)
    no_urls = sum(row["lookup_status"] == "no_url" for row in rows)
    exact_matches = sum(
        isinstance(row.get("content"), dict)
        and row["content"].get("benchmark_question_exact_match") is True
        for row in rows
    )
    covered_questions = {
        str(row["question_id"])
        for row in rows
        if row["lookup_status"] == "capture"
    }
    summary: dict[str, object] = {
        "schema_version": 2,
        "purpose": "historical-validity-source-discovery-v2",
        "candidate_rows": len(frame),
        "candidate_sha256": candidate_sha256,
        "v1_artifact_digest": V1_ARTIFACT_DIGEST,
        "v2_protocol_commit": V2_PROTOCOL_COMMIT,
        "v2_clarification_commit": V2_CLARIFICATION_COMMIT,
        "code_commit": code_commit,
        "lookup_rows": len(rows),
        "captures_with_frozen_content": captures,
        "questions_with_capture": len(covered_questions),
        "transport_failures": transport_failures,
        "content_failures": content_failures,
        "no_capture": no_captures,
        "no_url": no_urls,
        "exact_question_match_diagnostics": exact_matches,
        "commoncrawl_max_collections": COMMON_CRAWL_MAX_COLLECTIONS,
        "commoncrawl_collections_sha256": commoncrawl_collections_sha256,
    }
    _atomic_json(output_directory / "source-discovery-v2-summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expand frozen historical-validity source discovery")
    parser.add_argument("candidates_csv", type=Path)
    parser.add_argument("v1_locators_jsonl", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    with WaybackV2Provider() as wayback, CommonCrawlV2Provider(
        minimum_interval_seconds=0.5,
        retry_backoff_seconds=1.0,
    ) as commoncrawl:
        collections, collections_sha = commoncrawl.collections_manifest()
        summary = discover_v2_sources(
            candidates_csv=args.candidates_csv,
            v1_locators_jsonl=args.v1_locators_jsonl,
            output_directory=args.output_directory,
            providers=[wayback, commoncrawl],
            code_commit=args.code_commit,
            commoncrawl_collections=collections,
            commoncrawl_collections_sha256=collections_sha,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
