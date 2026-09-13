from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import pandas as pd

from prediction_lab.capture_index_client import CommonCrawlTransportError
from prediction_lab.commoncrawl_evidence import _utc_timestamp

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"


# The shared resumable stage currently recognizes CommonCrawlTransportError as its
# provider-transport boundary. Subclassing preserves that safety behavior without
# broadening the stage to swallow arbitrary historical-evidence errors.
class WaybackTransportError(CommonCrawlTransportError):
    """Raised when Wayback/CDX cannot make a reliable coverage decision."""


@dataclass(frozen=True)
class WaybackCapture:
    timestamp: pd.Timestamp
    url: str
    digest: str
    length: int | None
    mime: str
    status: str
    replay_url: str

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


def _normalized_host(value: str) -> str:
    host = value.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def same_exact_page(requested_url: str, captured_url: str) -> bool:
    """Accept scheme/www variation while requiring the same article path and query."""
    try:
        requested = urlparse(requested_url)
        captured = urlparse(captured_url)
    except ValueError:
        return False
    if _normalized_host(requested.netloc) != _normalized_host(captured.netloc):
        return False
    if (requested.path or "/") != (captured.path or "/"):
        return False
    if requested.query and requested.query != captured.query:
        return False
    return True


def _response_excerpt(response: httpx.Response, *, limit: int = 180) -> str:
    return " ".join(response.text.split())[:limit]


class WaybackCdxClient:
    """Rate-aware Wayback CDX client for exact pre-cutoff capture discovery."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = WAYBACK_CDX,
        timeout_seconds: float = 30.0,
        user_agent: str = "trading-prediction-lab/0.1 historical-evidence-research",
        retries: int = 3,
        retry_backoff_seconds: float = 3.0,
        minimum_interval_seconds: float = 3.0,
        result_limit: int = 1000,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds cannot be negative")
        if result_limit < 1:
            raise ValueError("result_limit must be positive")
        self.endpoint = endpoint
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.minimum_interval_seconds = minimum_interval_seconds
        self.result_limit = result_limit
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
        )
        self._headers = {"User-Agent": user_agent}
        self._last_request_at: float | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> WaybackCdxClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _pace(self) -> None:
        if self.minimum_interval_seconds == 0 or self._last_request_at is None:
            return
        remaining = self.minimum_interval_seconds - (
            time.monotonic() - self._last_request_at
        )
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, *, params: list[tuple[str, str]]) -> httpx.Response:
        last_error: Exception | None = None
        last_response: httpx.Response | None = None

        for attempt in range(self.retries):
            self._pace()
            retry_delay = self.retry_backoff_seconds * (2**attempt)
            try:
                response = self._client.get(
                    self.endpoint,
                    params=params,
                    headers=self._headers,
                )
                self._last_request_at = time.monotonic()
                if response.status_code != 429 and response.status_code < 500:
                    return response
                last_response = response
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        retry_delay = min(60.0, max(0.0, float(retry_after)))
                    except ValueError:
                        pass
            except httpx.HTTPError as exc:
                self._last_request_at = time.monotonic()
                last_error = exc

            if attempt + 1 < self.retries and retry_delay > 0:
                time.sleep(retry_delay)

        if last_response is not None:
            detail = _response_excerpt(last_response)
            suffix = f": {detail}" if detail else ""
            raise WaybackTransportError(
                f"Wayback CDX HTTP {last_response.status_code} after retries{suffix}"
            )
        raise WaybackTransportError(f"Wayback CDX request failed: {last_error}")

    @staticmethod
    def _records(payload: object) -> list[dict[str, Any]]:
        if payload == []:
            return []
        if not isinstance(payload, list) or not payload:
            raise WaybackTransportError("Wayback CDX response is not a JSON table")
        header = payload[0]
        if not isinstance(header, list) or not all(isinstance(item, str) for item in header):
            raise WaybackTransportError("Wayback CDX response has no valid header")
        records: list[dict[str, Any]] = []
        for values in payload[1:]:
            if isinstance(values, list) and len(values) == len(header):
                records.append(dict(zip(header, values, strict=True)))
        return records

    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int = 1,
    ) -> WaybackCapture | None:
        del max_collections
        cutoff_at = _utc_timestamp(cutoff, field="capture cutoff")
        params = [
            ("url", url),
            ("output", "json"),
            ("fl", "timestamp,original,mimetype,statuscode,digest,length"),
            ("filter", "statuscode:200"),
            ("filter", "mimetype:text/html"),
            ("matchType", "exact"),
            ("to", cutoff_at.strftime("%Y%m%d%H%M%S")),
            ("limit", str(self.result_limit)),
        ]
        response = self._get(params=params)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            detail = _response_excerpt(response)
            suffix = f": {detail}" if detail else ""
            raise WaybackTransportError(
                f"Wayback CDX HTTP {response.status_code}{suffix}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise WaybackTransportError("Wayback CDX returned invalid JSON") from exc

        candidates: list[WaybackCapture] = []
        for record in self._records(payload):
            try:
                timestamp = pd.to_datetime(
                    str(record["timestamp"]),
                    format="%Y%m%d%H%M%S",
                    utc=True,
                )
            except (KeyError, TypeError, ValueError):
                continue
            original = str(record.get("original") or "")
            mime = str(record.get("mimetype") or "")
            status = str(record.get("statuscode") or "")
            if timestamp > cutoff_at:
                continue
            if not same_exact_page(url, original):
                continue
            if status != "200" or "html" not in mime.lower():
                continue
            raw_length = record.get("length")
            try:
                length = int(raw_length) if raw_length not in {None, ""} else None
            except (TypeError, ValueError):
                length = None
            candidates.append(
                WaybackCapture(
                    timestamp=timestamp,
                    url=original,
                    digest=str(record.get("digest") or ""),
                    length=length,
                    mime=mime,
                    status=status,
                    replay_url=(
                        "https://web.archive.org/web/"
                        f"{timestamp.strftime('%Y%m%d%H%M%S')}id_/{original}"
                    ),
                )
            )

        if not candidates:
            return None
        return max(candidates, key=lambda item: item.timestamp)
