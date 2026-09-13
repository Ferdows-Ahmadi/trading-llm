"""Discover and freeze historical contract sources for fresh development candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
import pandas as pd

from prediction_lab.research_types import ResearchContractError, canonical_json_bytes
from prediction_lab.wayback_content import WaybackReplayClient, extract_archived_html_text

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
WAYBACK_CDX_URL = "https://web.archive.org/cdx/search/cdx"
CANDIDATE_SHA256 = "6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21"
CANDIDATE_ROWS = 64
PARENT_PREREGISTRATION_COMMIT = "c3a66d28d7126155935ccdd255034e7560dce6f0"
SOURCE_DISCOVERY_PROTOCOL_COMMIT = "4cceb901a29553ccad7b1e150558ee57906c12f1"

_LOCATOR_MARKET_FIELDS = (
    "id",
    "conditionId",
    "question",
    "slug",
    "description",
    "resolutionSource",
    "createdAt",
    "startDate",
    "endDate",
    "closedTime",
    "updatedAt",
)
_LOCATOR_EVENT_FIELDS = (
    "id",
    "slug",
    "title",
    "description",
    "createdAt",
    "startDate",
    "endDate",
    "updatedAt",
)
_ALLOWED_CANDIDATE_COLUMNS = (
    "question_id",
    "question_text",
    "forecasted_at",
    "source_cutoff_at",
    "event_id",
    "category",
)


class HistoricalSourceError(ResearchContractError):
    """Raised when historical source discovery violates its frozen contract."""


class SourceTransportError(HistoricalSourceError):
    """Raised when a remote source cannot make a reliable coverage decision."""


@dataclass(frozen=True)
class AuditCapture:
    timestamp: pd.Timestamp
    original: str
    mime: str
    status: str
    digest: str
    length: int | None
    replay_url: str

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "original": self.original,
            "mime": self.mime,
            "status": self.status,
            "digest": self.digest,
            "length": self.length,
            "replay_url": self.replay_url,
        }


class LocatorLookup(Protocol):
    def fetch_market(self, market_id: str) -> dict[str, object]: ...


class CaptureLookup(Protocol):
    def latest_capture_before(self, url: str, *, cutoff: object) -> AuditCapture | None: ...


class ReplayLookup(Protocol):
    def fetch(self, replay_url: str) -> httpx.Response: ...


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize_contract_text(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(text.split()).strip()


def _safe_text_hash(value: object) -> str | None:
    text = normalize_contract_text(value)
    if not text:
        return None
    return _sha256(text.encode("utf-8"))


def _safe_market_id(value: object) -> str:
    market_id = str(value).strip()
    if not re.fullmatch(r"[0-9]+", market_id):
        raise HistoricalSourceError(f"Candidate market ID is not numeric: {market_id!r}")
    return market_id


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _redact_locator(raw: dict[str, Any], *, market_id: str) -> dict[str, object]:
    if str(raw.get("id") or "") != market_id:
        raise HistoricalSourceError("Gamma locator returned the wrong market ID")
    market = {field: raw.get(field) for field in _LOCATOR_MARKET_FIELDS if field in raw}
    events: list[dict[str, object]] = []
    raw_events = raw.get("events")
    if isinstance(raw_events, list):
        for item in raw_events:
            if not isinstance(item, dict):
                continue
            events.append({field: item.get(field) for field in _LOCATOR_EVENT_FIELDS if field in item})
    return {"market": market, "events": events}


class GammaLocatorClient:
    """Fetch current Gamma metadata strictly as a historical-source locator."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        base_url: str = GAMMA_BASE_URL,
        timeout_seconds: float = 30.0,
        retries: int = 3,
        backoff_seconds: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GammaLocatorClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        last_response: httpx.Response | None = None
        for attempt in range(self.retries):
            try:
                response = self._client.get(url)
                if response.status_code != 429 and response.status_code < 500:
                    return response
                last_response = response
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt + 1 < self.retries:
                time.sleep(self.backoff_seconds * (2**attempt))
        if last_response is not None:
            raise SourceTransportError(
                f"Gamma HTTP {last_response.status_code} after {self.retries} attempts"
            )
        raise SourceTransportError(f"Gamma request failed: {last_error}")

    def fetch_market(self, market_id: str) -> dict[str, object]:
        market_id = _safe_market_id(market_id)
        direct = self._request(f"{self.base_url}/markets/{market_id}")
        if direct.status_code == 404:
            fallback = self._request(f"{self.base_url}/markets?id={market_id}")
            if fallback.status_code >= 400:
                raise HistoricalSourceError(f"Gamma fallback HTTP {fallback.status_code}")
            try:
                payload = fallback.json()
            except ValueError as exc:
                raise HistoricalSourceError("Gamma fallback returned invalid JSON") from exc
            if not isinstance(payload, list):
                raise HistoricalSourceError("Gamma fallback must return a list")
            matches = [item for item in payload if isinstance(item, dict) and str(item.get("id")) == market_id]
            if len(matches) != 1:
                raise HistoricalSourceError("Gamma fallback did not resolve exactly one market")
            return _redact_locator(matches[0], market_id=market_id)
        if direct.status_code >= 400:
            raise HistoricalSourceError(f"Gamma direct endpoint HTTP {direct.status_code}")
        try:
            payload = direct.json()
        except ValueError as exc:
            raise HistoricalSourceError("Gamma direct endpoint returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise HistoricalSourceError("Gamma direct endpoint must return an object")
        return _redact_locator(payload, market_id=market_id)


def _normalized_host(value: str) -> str:
    host = value.lower()
    return host[4:] if host.startswith("www.") else host


def same_logical_url(requested_url: str, captured_url: str) -> bool:
    try:
        requested = urlparse(requested_url)
        captured = urlparse(captured_url)
    except ValueError:
        return False
    return (
        _normalized_host(requested.netloc) == _normalized_host(captured.netloc)
        and (requested.path or "/") == (captured.path or "/")
        and requested.query == captured.query
    )


class WaybackAuditCdxClient:
    """Discover latest exact pre-cutoff HTML/JSON captures for audit sources."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = WAYBACK_CDX_URL,
        timeout_seconds: float = 30.0,
        retries: int = 3,
        backoff_seconds: float = 2.0,
        minimum_interval_seconds: float = 0.75,
        result_limit: int = 1000,
    ) -> None:
        self.endpoint = endpoint
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.minimum_interval_seconds = minimum_interval_seconds
        self.result_limit = result_limit
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self._last_request_at: float | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> WaybackAuditCdxClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _pace(self) -> None:
        if self._last_request_at is None or self.minimum_interval_seconds <= 0:
            return
        remaining = self.minimum_interval_seconds - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, params: list[tuple[str, str]]) -> httpx.Response:
        last_error: Exception | None = None
        last_response: httpx.Response | None = None
        for attempt in range(self.retries):
            self._pace()
            try:
                response = self._client.get(self.endpoint, params=params)
                self._last_request_at = time.monotonic()
                if response.status_code != 429 and response.status_code < 500:
                    return response
                last_response = response
            except httpx.HTTPError as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
            if attempt + 1 < self.retries:
                time.sleep(self.backoff_seconds * (2**attempt))
        if last_response is not None:
            raise SourceTransportError(
                f"Wayback CDX HTTP {last_response.status_code} after retries"
            )
        raise SourceTransportError(f"Wayback CDX request failed: {last_error}")

    def latest_capture_before(self, url: str, *, cutoff: object) -> AuditCapture | None:
        cutoff_at = pd.Timestamp(cutoff)
        cutoff_at = cutoff_at.tz_localize("UTC") if cutoff_at.tzinfo is None else cutoff_at.tz_convert("UTC")
        params = [
            ("url", url),
            ("output", "json"),
            ("fl", "timestamp,original,mimetype,statuscode,digest,length"),
            ("filter", "statuscode:200"),
            ("matchType", "exact"),
            ("to", cutoff_at.strftime("%Y%m%d%H%M%S")),
            ("limit", str(self.result_limit)),
        ]
        response = self._get(params)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise SourceTransportError(f"Wayback CDX HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceTransportError("Wayback CDX returned invalid JSON") from exc
        if payload == []:
            return None
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
            raise SourceTransportError("Wayback CDX response is not a JSON table")
        header = payload[0]
        if not all(isinstance(item, str) for item in header):
            raise SourceTransportError("Wayback CDX header is malformed")
        captures: list[AuditCapture] = []
        for values in payload[1:]:
            if not isinstance(values, list) or len(values) != len(header):
                continue
            record = dict(zip(header, values, strict=True))
            try:
                timestamp = pd.to_datetime(str(record["timestamp"]), format="%Y%m%d%H%M%S", utc=True)
            except (KeyError, TypeError, ValueError):
                continue
            original = str(record.get("original") or "")
            mime = str(record.get("mimetype") or "").lower()
            status = str(record.get("statuscode") or "")
            if timestamp > cutoff_at or not same_logical_url(url, original):
                continue
            if status != "200" or not ("html" in mime or "json" in mime):
                continue
            raw_length = record.get("length")
            try:
                length = int(raw_length) if raw_length not in {None, ""} else None
            except (TypeError, ValueError):
                length = None
            captures.append(
                AuditCapture(
                    timestamp=timestamp,
                    original=original,
                    mime=mime,
                    status=status,
                    digest=str(record.get("digest") or ""),
                    length=length,
                    replay_url=(
                        "https://web.archive.org/web/"
                        f"{timestamp.strftime('%Y%m%d%H%M%S')}id_/{original}"
                    ),
                )
            )
        return max(captures, key=lambda item: item.timestamp) if captures else None


def locator_urls(market_id: str, locator: dict[str, object]) -> list[tuple[str, str]]:
    market_id = _safe_market_id(market_id)
    urls = [
        ("gamma-direct", f"{GAMMA_BASE_URL}/markets/{market_id}"),
        ("gamma-query", f"{GAMMA_BASE_URL}/markets?id={market_id}"),
    ]
    events = locator.get("events")
    if isinstance(events, list):
        slugs = sorted(
            {
                str(item.get("slug") or "").strip()
                for item in events
                if isinstance(item, dict) and str(item.get("slug") or "").strip()
            }
        )
        for slug in slugs:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", slug):
                raise HistoricalSourceError(f"Unsafe event slug from Gamma: {slug!r}")
            urls.append((f"event:{slug}", f"https://polymarket.com/event/{slug}"))
    return urls


def _historical_gamma_object(payload: object, market_id: str) -> dict[str, Any] | None:
    if isinstance(payload, dict) and str(payload.get("id") or "") == market_id:
        return payload
    if isinstance(payload, list):
        matches = [item for item in payload if isinstance(item, dict) and str(item.get("id") or "") == market_id]
        if len(matches) == 1:
            return matches[0]
    return None


def _freeze_replay(
    *,
    response: httpx.Response,
    capture: AuditCapture,
    market_id: str,
    benchmark_question: str,
    raw_directory: Path,
    text_directory: Path,
) -> dict[str, object]:
    raw = response.content
    if not raw:
        raise HistoricalSourceError("Wayback replay body is empty")
    raw_sha = _sha256(raw)
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = raw_directory / f"{raw_sha}.bin"
    if not raw_path.exists():
        raw_path.write_bytes(raw)

    benchmark_normalized = normalize_contract_text(benchmark_question)
    diagnostic: dict[str, object] = {
        "raw_sha256": raw_sha,
        "raw_bytes": len(raw),
        "benchmark_question_normalized_sha256": _sha256(benchmark_normalized.encode("utf-8")),
    }
    if "json" in capture.mime:
        try:
            payload = response.json()
        except ValueError as exc:
            raise HistoricalSourceError("Archived Gamma response is not valid JSON") from exc
        diagnostic["canonical_json_sha256"] = _sha256(canonical_json_bytes(payload))
        historical = _historical_gamma_object(payload, market_id)
        if historical is not None:
            historical_question = normalize_contract_text(historical.get("question") or "")
            diagnostic["historical_question_sha256"] = (
                _sha256(historical_question.encode("utf-8")) if historical_question else None
            )
            diagnostic["benchmark_question_exact_match"] = historical_question == benchmark_normalized
            diagnostic["historical_description_sha256"] = _safe_text_hash(
                historical.get("description") or historical.get("rules") or ""
            )
            diagnostic["historical_resolution_source"] = str(
                historical.get("resolutionSource") or ""
            ).strip()
        else:
            diagnostic["benchmark_question_exact_match"] = False
            diagnostic["historical_market_object_found"] = False
    else:
        text = extract_archived_html_text(response.text)
        text_sha = _sha256(text.encode("utf-8"))
        text_directory.mkdir(parents=True, exist_ok=True)
        text_path = text_directory / f"{text_sha}.txt"
        if not text_path.exists():
            text_path.write_text(text, encoding="utf-8")
        diagnostic["text_sha256"] = text_sha
        diagnostic["text_chars"] = len(text)
        diagnostic["benchmark_question_exact_match"] = benchmark_normalized in normalize_contract_text(text)
    return diagnostic


def discover_sources(
    *,
    candidates_csv: Path,
    output_directory: Path,
    locator_client: LocatorLookup,
    cdx_client: CaptureLookup,
    replay_client: ReplayLookup,
    code_commit: str,
) -> dict[str, object]:
    if _sha256(candidates_csv.read_bytes()) != CANDIDATE_SHA256:
        raise HistoricalSourceError("Fresh candidate CSV digest changed")
    frame = pd.read_csv(candidates_csv, dtype={"question_id": str})
    if len(frame) != CANDIDATE_ROWS or tuple(frame.columns) != _ALLOWED_CANDIDATE_COLUMNS:
        raise HistoricalSourceError("Fresh candidate artifact shape changed")

    output = output_directory
    raw_directory = output / "raw"
    text_directory = output / "text"
    output.mkdir(parents=True, exist_ok=True)
    locator_rows: list[dict[str, object]] = []
    lookup_rows: list[dict[str, object]] = []

    for row in frame.itertuples(index=False):
        market_id = _safe_market_id(row.question_id)
        forecasted_at = pd.Timestamp(row.forecasted_at)
        forecasted_at = (
            forecasted_at.tz_localize("UTC")
            if forecasted_at.tzinfo is None
            else forecasted_at.tz_convert("UTC")
        )
        locator_status = "success"
        locator_error: str | None = None
        locator: dict[str, object] | None = None
        try:
            locator = locator_client.fetch_market(market_id)
        except (HistoricalSourceError, httpx.HTTPError) as exc:
            locator_status = "failure"
            locator_error = f"{type(exc).__name__}: {exc}"
        locator_rows.append(
            {
                "question_id": market_id,
                "event_id": str(row.event_id),
                "forecasted_at": forecasted_at.isoformat(),
                "benchmark_question_sha256": _safe_text_hash(row.question_text),
                "locator_status": locator_status,
                "locator_error": locator_error,
                "locator": locator,
            }
        )
        if locator is None:
            continue

        for pattern, url in locator_urls(market_id, locator):
            record: dict[str, object] = {
                "question_id": market_id,
                "event_id": str(row.event_id),
                "forecasted_at": forecasted_at.isoformat(),
                "pattern": pattern,
                "url": url,
                "lookup_status": "no_capture",
                "error": None,
                "capture": None,
                "replay": None,
            }
            try:
                capture = cdx_client.latest_capture_before(url, cutoff=forecasted_at)
                if capture is not None:
                    record["capture"] = capture.to_dict()
                    record["lookup_status"] = "capture"
                    try:
                        response = replay_client.fetch(capture.replay_url)
                        record["replay"] = _freeze_replay(
                            response=response,
                            capture=capture,
                            market_id=market_id,
                            benchmark_question=str(row.question_text),
                            raw_directory=raw_directory,
                            text_directory=text_directory,
                        )
                    except (HistoricalSourceError, httpx.HTTPError) as exc:
                        record["lookup_status"] = "replay_failure"
                        record["error"] = f"{type(exc).__name__}: {exc}"
            except (HistoricalSourceError, httpx.HTTPError) as exc:
                record["lookup_status"] = "transport_failure"
                record["error"] = f"{type(exc).__name__}: {exc}"
            lookup_rows.append(record)

    (output / "locators.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in locator_rows),
        encoding="utf-8",
    )
    (output / "wayback-lookups.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in lookup_rows),
        encoding="utf-8",
    )

    successful_locators = sum(row["locator_status"] == "success" for row in locator_rows)
    captures = sum(row["lookup_status"] == "capture" for row in lookup_rows)
    replay_failures = sum(row["lookup_status"] == "replay_failure" for row in lookup_rows)
    transport_failures = sum(row["lookup_status"] == "transport_failure" for row in lookup_rows)
    exact_matches = sum(
        isinstance(row.get("replay"), dict)
        and row["replay"].get("benchmark_question_exact_match") is True
        for row in lookup_rows
    )
    summary: dict[str, object] = {
        "schema_version": 1,
        "purpose": "historical-validity-source-discovery-v1",
        "candidate_rows": len(frame),
        "candidate_sha256": CANDIDATE_SHA256,
        "successful_locators": successful_locators,
        "locator_failures": len(frame) - successful_locators,
        "url_patterns_attempted": len(lookup_rows),
        "captures_with_frozen_replay": captures,
        "replay_failures": replay_failures,
        "transport_failures": transport_failures,
        "exact_question_match_diagnostics": exact_matches,
        "parent_preregistration_commit": PARENT_PREREGISTRATION_COMMIT,
        "source_discovery_protocol_commit": SOURCE_DISCOVERY_PROTOCOL_COMMIT,
        "code_commit": code_commit,
    }
    _atomic_json(output / "source-discovery-summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze historical-validity source discovery")
    parser.add_argument("candidates_csv", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    with GammaLocatorClient() as locator, WaybackAuditCdxClient() as cdx, WaybackReplayClient(
        minimum_interval_seconds=0.5
    ) as replay:
        summary = discover_sources(
            candidates_csv=args.candidates_csv,
            output_directory=args.output_directory,
            locator_client=locator,
            cdx_client=cdx,
            replay_client=replay,
            code_commit=args.code_commit,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
