from __future__ import annotations

import json
import time
from urllib.parse import urlparse

import httpx

from prediction_lab.commoncrawl_evidence import (
    CommonCrawlCapture,
    CommonCrawlClient,
    HistoricalEvidenceError,
    _utc_timestamp,
)


class CommonCrawlTransportError(HistoricalEvidenceError):
    """Raised when Common Crawl transport prevents a reliable coverage decision."""


def _normalized_host(value: str) -> str:
    host = value.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def canonical_index_key(url: str) -> str:
    """Return one scheme-less exact-page CDX key for an article URL."""
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise HistoricalEvidenceError(f"Invalid article URL: {url!r}") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HistoricalEvidenceError(f"Invalid article URL: {url!r}")
    host = _normalized_host(parsed.netloc)
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path}{query}"


def _same_exact_page(requested_url: str, captured_url: str) -> bool:
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


class CaptureIndexCommonCrawlClient(CommonCrawlClient):
    """Rate-aware Common Crawl CDX client for exact pre-cutoff capture discovery."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        index_url: str = "https://index.commoncrawl.org",
        timeout_seconds: float = 20.0,
        user_agent: str = "trading-prediction-lab/0.1 historical-evidence-research",
        retries: int = 3,
        retry_backoff_seconds: float = 2.0,
        minimum_interval_seconds: float = 2.0,
    ) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds cannot be negative")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        super().__init__(
            client=client,
            index_url=index_url,
            timeout_seconds=timeout_seconds,
            user_agent=user_agent,
            retries=retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_request_at: float | None = None

    def _pace(self) -> None:
        if self.minimum_interval_seconds == 0 or self._last_request_at is None:
            return
        remaining = self.minimum_interval_seconds - (
            time.monotonic() - self._last_request_at
        )
        if remaining > 0:
            time.sleep(remaining)

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
            self._pace()
            retry_delay = self.retry_backoff_seconds * (2**attempt)
            try:
                response = self._client.get(url, params=params, headers=headers)
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
            raise CommonCrawlTransportError(
                f"Common Crawl HTTP {last_response.status_code} after retries"
            )
        raise CommonCrawlTransportError(f"Common Crawl request failed: {last_error}")

    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int = 3,
    ) -> CommonCrawlCapture | None:
        cutoff_at = _utc_timestamp(cutoff, field="capture cutoff")
        index_key = canonical_index_key(url)
        transport_errors: list[str] = []

        for collection in self._eligible_collections(
            cutoff_at,
            max_collections=max_collections,
        ):
            crawl_id = str(collection["id"])
            endpoint = str(
                collection.get("cdx-api")
                or f"{self.index_url}/{crawl_id}-index"
            )
            try:
                response = self._get(
                    endpoint,
                    params={
                        "url": index_key,
                        "output": "json",
                        "matchType": "exact",
                    },
                    headers=self._headers,
                )
            except CommonCrawlTransportError as exc:
                transport_errors.append(f"{crawl_id}: {exc}")
                continue

            if response.status_code == 404:
                continue
            if response.status_code >= 400:
                raise HistoricalEvidenceError(
                    f"Common Crawl index returned HTTP {response.status_code}"
                )

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
                if not _same_exact_page(url, capture.url):
                    continue
                if capture.timestamp > cutoff_at:
                    continue
                if capture.status != "200" or "html" not in capture.mime.lower():
                    continue
                valid.append(capture)

            if valid:
                return max(valid, key=lambda item: item.timestamp)

        if transport_errors:
            raise CommonCrawlTransportError(
                "Common Crawl lookup incomplete because of transport errors: "
                + " | ".join(transport_errors[:3])
            )
        return None
