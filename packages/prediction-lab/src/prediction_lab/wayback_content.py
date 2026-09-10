from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from prediction_lab.research_types import EvidenceItem, ResearchContractError, parse_utc


class WaybackContentError(ResearchContractError):
    """Raised when an archived page cannot be frozen as trustworthy historical evidence."""


class WaybackReplayTransportError(WaybackContentError):
    """Raised when replay transport is inconclusive."""


@dataclass(frozen=True)
class FrozenArchivedContent:
    question_id: str
    event_id: str
    source_cutoff_at: str
    article_url: str
    article_title: str
    capture_timestamp: str
    replay_url: str
    archive_digest: str
    raw_sha256: str
    raw_bytes: int
    text_sha256: str
    text_chars: int
    retrieved_at: str
    text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "archive_digest": self.archive_digest,
            "article_title": self.article_title,
            "article_url": self.article_url,
            "capture_timestamp": self.capture_timestamp,
            "event_id": self.event_id,
            "question_id": self.question_id,
            "raw_bytes": self.raw_bytes,
            "raw_sha256": self.raw_sha256,
            "replay_url": self.replay_url,
            "retrieved_at": self.retrieved_at,
            "source_cutoff_at": self.source_cutoff_at,
            "text": self.text,
            "text_chars": self.text_chars,
            "text_sha256": self.text_sha256,
        }


class _ArticleTextParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
    _BREAK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        lowered = tag.lower()
        if lowered in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth == 0 and lowered in self._BREAK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if self._skip_depth == 0 and lowered in self._BREAK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts).replace("\r", "\n")
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.split("\n")]
        compact: list[str] = []
        for line in lines:
            if not line:
                if compact and compact[-1] != "":
                    compact.append("")
                continue
            compact.append(line)
        return "\n".join(compact).strip()


def extract_archived_html_text(html: str) -> str:
    parser = _ArticleTextParser()
    parser.feed(html)
    parser.close()
    return parser.text()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_capture_rows(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WaybackContentError(
                f"Malformed capture JSONL at line {line_number}"
            ) from exc
        if not isinstance(record, dict):
            raise WaybackContentError(
                f"Capture JSONL line {line_number} is not an object"
            )
        rows.append(record)
    return rows


def _checkpoint_name(question_id: str, article_url: str, capture_timestamp: str) -> str:
    material = f"{question_id}\n{article_url}\n{capture_timestamp}".encode()
    return hashlib.sha256(material).hexdigest() + ".json"


def _snapshot_path_timestamp(replay_url: str) -> str | None:
    try:
        parsed = urlparse(replay_url)
    except ValueError:
        return None
    if parsed.netloc.lower() != "web.archive.org":
        return None
    match = re.match(r"^/web/(\d{14})id_/", parsed.path)
    return match.group(1) if match else None


class WaybackReplayClient:
    """Fetch exact Wayback snapshots without following redirects to different resources."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
        user_agent: str = "trading-prediction-lab/0.1 historical-evidence-research",
        retries: int = 3,
        retry_backoff_seconds: float = 3.0,
        minimum_interval_seconds: float = 2.0,
    ) -> None:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative")
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds cannot be negative")
        self.retries = retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.minimum_interval_seconds = minimum_interval_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=False)
        self._headers = {"User-Agent": user_agent}
        self._last_request_at: float | None = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> WaybackReplayClient:
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

    def fetch(self, replay_url: str) -> httpx.Response:
        expected_timestamp = _snapshot_path_timestamp(replay_url)
        if expected_timestamp is None:
            raise WaybackContentError(f"Unsafe Wayback replay URL: {replay_url!r}")

        last_response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self._pace()
            retry_delay = self.retry_backoff_seconds * (2**attempt)
            try:
                response = self._client.get(replay_url, headers=self._headers)
                self._last_request_at = time.monotonic()
                if response.status_code == 200:
                    final_timestamp = _snapshot_path_timestamp(str(response.url))
                    if final_timestamp != expected_timestamp:
                        raise WaybackContentError(
                            "Wayback replay changed the frozen capture timestamp"
                        )
                    return response
                if 300 <= response.status_code < 400:
                    location = response.headers.get("Location", "")
                    raise WaybackContentError(
                        f"Wayback replay redirected instead of serving exact snapshot: {location}"
                    )
                if response.status_code != 429 and response.status_code < 500:
                    raise WaybackContentError(
                        f"Wayback replay HTTP {response.status_code}"
                    )
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
            raise WaybackReplayTransportError(
                f"Wayback replay HTTP {last_response.status_code} after retries"
            )
        raise WaybackReplayTransportError(f"Wayback replay request failed: {last_error}")


def freeze_wayback_content(
    *,
    captures_jsonl: str | Path,
    output_directory: str | Path,
    replay_client: WaybackReplayClient,
    max_items_per_question: int = 1,
    minimum_text_chars: int = 200,
) -> dict[str, object]:
    """Fetch verified snapshots and freeze raw HTML, extracted text, and evidence fixture."""
    if max_items_per_question < 1:
        raise ValueError("max_items_per_question must be positive")
    if minimum_text_chars < 1:
        raise ValueError("minimum_text_chars must be positive")

    captures = _load_capture_rows(captures_jsonl)
    output = Path(output_directory)
    checkpoints = output / "checkpoints"
    raw_directory = output / "raw"
    text_directory = output / "text"
    for directory in (checkpoints, raw_directory, text_directory):
        directory.mkdir(parents=True, exist_ok=True)

    selected: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_question_ids = {str(row.get("question_id") or "") for row in captures}
    for row in captures:
        if row.get("lookup_status") != "capture" or not row.get("capture_found"):
            continue
        question_id = str(row.get("question_id") or "")
        if not question_id or len(selected[question_id]) >= max_items_per_question:
            continue
        capture = row.get("capture")
        if not isinstance(capture, dict):
            raise WaybackContentError(f"Capture row for {question_id} has no capture object")
        selected[question_id].append(row)

    frozen_records: list[dict[str, object]] = []
    evidence_by_question: dict[str, list[EvidenceItem]] = {
        question_id: [] for question_id in all_question_ids if question_id
    }
    reused = 0
    attempted = 0
    failures = 0

    for question_id in sorted(selected):
        for row in selected[question_id]:
            capture = row["capture"]
            assert isinstance(capture, dict)
            article_url = str(row.get("article_url") or "").strip()
            article_title = str(row.get("article_title") or "").strip() or article_url
            source_cutoff = parse_utc(row.get("source_cutoff_at"), field="source_cutoff_at")
            capture_at = parse_utc(capture.get("timestamp"), field="capture timestamp")
            if capture_at > source_cutoff:
                raise WaybackContentError(
                    f"Post-cutoff capture reached content stage for question {question_id}"
                )
            replay_url = str(capture.get("replay_url") or "").strip()
            expected_snapshot = capture_at.strftime("%Y%m%d%H%M%S")
            if _snapshot_path_timestamp(replay_url) != expected_snapshot:
                raise WaybackContentError(
                    f"Replay URL timestamp mismatch for question {question_id}"
                )

            checkpoint = checkpoints / _checkpoint_name(
                question_id,
                article_url,
                capture_at.isoformat(),
            )
            if checkpoint.exists():
                cached = json.loads(checkpoint.read_text(encoding="utf-8"))
                if not isinstance(cached, dict):
                    raise WaybackContentError("Content checkpoint must be an object")
                if cached.get("status") == "content":
                    record = cached.get("record")
                    if not isinstance(record, dict):
                        raise WaybackContentError("Successful content checkpoint has no record")
                    text_sha256 = str(record.get("text_sha256") or "")
                    text_path = text_directory / f"{text_sha256}.txt"
                    if not text_path.exists():
                        raise WaybackContentError("Cached extracted text file is missing")
                    text = text_path.read_text(encoding="utf-8")
                    item = EvidenceItem.create(
                        source_id=str(cached["source_id"]),
                        source_type="wayback-archived-news",
                        uri_or_reference=article_url,
                        title=article_title,
                        available_at=capture_at,
                        retrieved_at=record.get("retrieved_at"),
                        text=text,
                        expected_content_hash=text_sha256,
                    )
                    evidence_by_question[question_id].append(item)
                    frozen_records.append(record)
                    reused += 1
                    continue

            attempted += 1
            try:
                response = replay_client.fetch(replay_url)
                content_type = response.headers.get("Content-Type", "").lower()
                if content_type and "html" not in content_type:
                    raise WaybackContentError(
                        f"Archived snapshot is not HTML: {content_type}"
                    )
                raw = response.content
                if not raw:
                    raise WaybackContentError("Archived snapshot body is empty")
                text = extract_archived_html_text(response.text)
                if len(text) < minimum_text_chars:
                    raise WaybackContentError(
                        f"Extracted archived text is too short: {len(text)} characters"
                    )
            except WaybackContentError as exc:
                failures += 1
                _atomic_json(
                    checkpoint,
                    {
                        "article_url": article_url,
                        "capture_timestamp": capture_at.isoformat(),
                        "error": f"{type(exc).__name__}: {exc}",
                        "question_id": question_id,
                        "status": "content_failure",
                    },
                )
                continue

            raw_sha256 = hashlib.sha256(raw).hexdigest()
            text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            raw_path = raw_directory / f"{raw_sha256}.html"
            text_path = text_directory / f"{text_sha256}.txt"
            if not raw_path.exists():
                raw_path.write_bytes(raw)
            if not text_path.exists():
                text_path.write_text(text, encoding="utf-8")

            retrieved_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            frozen = FrozenArchivedContent(
                question_id=question_id,
                event_id=str(row.get("event_id") or ""),
                source_cutoff_at=source_cutoff.isoformat().replace("+00:00", "Z"),
                article_url=article_url,
                article_title=article_title,
                capture_timestamp=capture_at.isoformat().replace("+00:00", "Z"),
                replay_url=replay_url,
                archive_digest=str(capture.get("digest") or ""),
                raw_sha256=raw_sha256,
                raw_bytes=len(raw),
                text_sha256=text_sha256,
                text_chars=len(text),
                retrieved_at=retrieved_at,
                text=text,
            )
            record = frozen.to_dict()
            source_material = f"{question_id}\n{article_url}\n{capture_at.isoformat()}"
            source_id = "wayback:" + hashlib.sha256(source_material.encode()).hexdigest()[:24]
            item = EvidenceItem.create(
                source_id=source_id,
                source_type="wayback-archived-news",
                uri_or_reference=article_url,
                title=article_title,
                available_at=capture_at,
                retrieved_at=retrieved_at,
                text=text,
                expected_content_hash=text_sha256,
            )
            evidence_by_question[question_id].append(item)
            frozen_records.append(record)
            _atomic_json(
                checkpoint,
                {
                    "article_url": article_url,
                    "capture_timestamp": capture_at.isoformat(),
                    "question_id": question_id,
                    "record": record,
                    "source_id": source_id,
                    "status": "content",
                },
            )

    frozen_records.sort(
        key=lambda record: (
            str(record["question_id"]),
            str(record["article_url"]),
            str(record["capture_timestamp"]),
        )
    )
    (output / "content.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in frozen_records
        ),
        encoding="utf-8",
    )
    fixture = {
        "questions": {
            question_id: [item.to_dict() for item in evidence_by_question[question_id]]
            for question_id in sorted(evidence_by_question)
        },
        "schema_version": 1,
    }
    _atomic_json(output / "evidence-fixture.json", fixture)
    fixture_sha256 = hashlib.sha256(
        (output / "evidence-fixture.json").read_bytes()
    ).hexdigest()
    summary: dict[str, object] = {
        "attempted_this_run": attempted,
        "content_failures": failures,
        "evidence_fixture_sha256": fixture_sha256,
        "frozen_items": len(frozen_records),
        "max_items_per_question": max_items_per_question,
        "questions_with_content": sum(bool(items) for items in evidence_by_question.values()),
        "reused_checkpoints": reused,
        "selected_capture_items": sum(len(items) for items in selected.values()),
    }
    _atomic_json(output / "content-summary.json", summary)
    return summary
