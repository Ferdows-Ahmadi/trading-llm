from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, cast

import httpx
import pandas as pd

from prediction_lab.capture_index_client import CommonCrawlTransportError
from prediction_lab.commoncrawl_evidence import (
    CommonCrawlCapture,
    HistoricalEvidenceError,
    select_parent_event_pilot,
)
from prediction_lab.datasets import verify_frozen_dataset
from prediction_lab.research_types import content_hash


class CaptureLookup(Protocol):
    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int,
    ) -> CommonCrawlCapture | None: ...


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _utc(value: object, *, field: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(cast(str, value))
    except (TypeError, ValueError) as exc:
        raise HistoricalEvidenceError(f"Invalid {field}: {value!r}") from exc
    if pd.isna(timestamp):
        raise HistoricalEvidenceError(f"Missing {field}")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _load_discovery(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HistoricalEvidenceError(
                f"Malformed discovery JSONL at line {line_number}"
            ) from exc
        if not isinstance(record, dict) or not record.get("question_id"):
            raise HistoricalEvidenceError(
                f"Discovery JSONL line {line_number} is missing question_id"
            )
        records.append(record)
    return records


def _checkpoint_name(question_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{question_id}\n{url}".encode()).hexdigest()
    return f"{digest}.json"


def _validate_cached_record(
    cached: object,
    *,
    question_id: str,
    url: str,
) -> dict[str, object]:
    if not isinstance(cached, dict):
        raise HistoricalEvidenceError("Capture checkpoint must contain a JSON object")
    if str(cached.get("question_id") or "") != question_id:
        raise HistoricalEvidenceError(f"Capture checkpoint question mismatch for {question_id}")
    if str(cached.get("article_url") or "") != url:
        raise HistoricalEvidenceError(f"Capture checkpoint URL mismatch for question {question_id}")
    return cached


def _cached_status(record: dict[str, object]) -> str:
    status = str(record.get("lookup_status") or "")
    if status in {"capture", "no_capture", "transport_failure"}:
        return status
    if record.get("error"):
        return "transport_failure"
    if bool(record.get("capture_found")):
        return "capture"
    return "no_capture"


def run_commoncrawl_capture_stage(
    *,
    development_csv: str | Path,
    development_manifest: str | Path,
    discovery_jsonl: str | Path,
    output_directory: str | Path,
    archive: CaptureLookup,
    pilot_size: int = 20,
    max_urls_per_question: int = 6,
    max_collections: int = 3,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Resolve exact pre-cutoff Common Crawl captures without fetching WARC bodies."""
    if pilot_size < 1:
        raise ValueError("pilot_size must be positive")
    if max_urls_per_question < 1:
        raise ValueError("max_urls_per_question must be positive")
    if max_collections < 1:
        raise ValueError("max_collections must be positive")

    development = verify_frozen_dataset(
        csv_path=development_csv,
        manifest_path=development_manifest,
    )
    split_values = set(development.get("split", pd.Series(dtype=str)).astype(str))
    if split_values != {"development"}:
        raise HistoricalEvidenceError("Capture stage accepts development rows only")

    pilot = select_parent_event_pilot(development, size=pilot_size)
    pilot_by_id = {str(row.question_id): row for row in pilot.itertuples(index=False)}
    discovery_records = _load_discovery(discovery_jsonl)
    discovery_by_id = {str(item["question_id"]): item for item in discovery_records}
    unexpected = sorted(set(discovery_by_id) - set(pilot_by_id))
    if unexpected:
        raise HistoricalEvidenceError(
            f"Discovery artifact contains questions outside frozen pilot: {unexpected[:3]}"
        )

    output = Path(output_directory)
    checkpoints = output / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    reused = 0
    attempted = 0
    retried_failed = 0

    for question_id, row in pilot_by_id.items():
        discovery = discovery_by_id.get(question_id)
        if discovery is None:
            discovery = {"source_cutoff_at": str(row.source_cutoff_at), "articles": []}
        first_row = len(rows)
        cutoff = _utc(row.source_cutoff_at, field="source_cutoff_at")
        artifact_cutoff = _utc(discovery.get("source_cutoff_at"), field="discovery cutoff")
        if artifact_cutoff != cutoff:
            raise HistoricalEvidenceError(f"Discovery cutoff mismatch for question {question_id}")
        raw_articles = discovery.get("articles", [])
        if not isinstance(raw_articles, list):
            raise HistoricalEvidenceError(
                f"Discovery articles for question {question_id} are not a list"
            )

        acquisition_context_hash = content_hash(
            {
                "discovery": discovery,
                "max_urls_per_question": max_urls_per_question,
                "max_collections": max_collections,
            }
        )
        seen_urls: set[str] = set()
        for raw_article in raw_articles:
            if len(seen_urls) >= max_urls_per_question:
                break
            if not isinstance(raw_article, dict):
                continue
            url = str(raw_article.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            checkpoint = checkpoints / _checkpoint_name(question_id, url)
            if checkpoint.exists():
                cached = _validate_cached_record(
                    json.loads(checkpoint.read_text(encoding="utf-8")),
                    question_id=question_id,
                    url=url,
                )
                status = _cached_status(cached)
                if status != "transport_failure":
                    if cached.get("lookup_status") != status:
                        cached["lookup_status"] = status
                        _atomic_write_json(checkpoint, cached)
                    cached["acquisition_state"] = (
                        "verified"
                        if cached.get("acquisition_context_hash") == acquisition_context_hash
                        else "unknown_incomplete"
                    )
                    rows.append(cached)
                    reused += 1
                    continue
                retried_failed += 1

            attempted += 1
            error: str | None = None
            capture: CommonCrawlCapture | None = None
            try:
                capture = archive.latest_capture_before(
                    url,
                    cutoff=cutoff,
                    max_collections=max_collections,
                )
            except (CommonCrawlTransportError, httpx.HTTPError) as exc:
                error = f"{type(exc).__name__}: {exc}"

            if capture is not None and capture.timestamp > cutoff:
                raise HistoricalEvidenceError(
                    f"Common Crawl returned post-cutoff capture for question {question_id}"
                )

            if error is not None:
                lookup_status = "transport_failure"
            elif capture is not None:
                lookup_status = "capture"
            else:
                lookup_status = "no_capture"

            record: dict[str, object] = {
                "question_id": question_id,
                "acquisition_context_hash": acquisition_context_hash,
                "event_id": str(row.event_id),
                "source_cutoff_at": cutoff.isoformat(),
                "article_url": url,
                "article_title": str(raw_article.get("title") or ""),
                "discovered_seen_at": str(raw_article.get("seen_at") or ""),
                "capture": capture.to_dict() if capture is not None else None,
                "capture_found": capture is not None,
                "lookup_status": lookup_status,
                "error": error,
            }
            _atomic_write_json(checkpoint, record)
            rows.append(record)

        question_rows = rows[first_row:]
        if (
            discovery.get("error")
            or discovery.get("acquisition_state") == "retrieval_failure"
            or any(r.get("error") for r in question_rows)
        ):
            acquisition_state = "retrieval_failure"
        elif (
            any(
                not isinstance(a, dict) or not str(a.get("url") or "").strip() for a in raw_articles
            )
            or discovery.get("acquisition_state") != "verified"
        ) or any(r.get("acquisition_state") == "unknown_incomplete" for r in question_rows):
            acquisition_state = "unknown_incomplete"
        else:
            acquisition_state = "verified"
        if not question_rows:
            # Keep missing/empty discovery in the per-question acquisition ledger.
            question_rows = [
                {
                    "question_id": question_id,
                    "event_id": str(row.event_id),
                    "source_cutoff_at": cutoff.isoformat(),
                    "article_url": "",
                    "capture_found": False,
                    "lookup_status": "not_attempted",
                    "error": discovery.get("error"),
                }
            ]
            rows.extend(question_rows)
        for question_record in question_rows:
            question_record["acquisition_state"] = acquisition_state

    rows.sort(
        key=lambda item: (
            str(item["question_id"]),
            str(item["article_url"]),
        )
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "captures.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in rows),
        encoding="utf-8",
    )

    audit = pd.DataFrame(
        {
            "question_id": [record["question_id"] for record in rows],
            "event_id": [record["event_id"] for record in rows],
            "article_url": [record["article_url"] for record in rows],
            "capture_found": [record["capture_found"] for record in rows],
            "lookup_status": [record["lookup_status"] for record in rows],
            "error": [record["error"] or "" for record in rows],
        }
    )
    audit.to_csv(output / "capture-audit.csv", index=False, lineterminator="\n")

    questions_with_discovery = sum(
        bool(discovery_by_id.get(question_id, {}).get("articles")) for question_id in pilot_by_id
    )
    captured_question_ids = {
        str(record["question_id"]) for record in rows if record["lookup_status"] == "capture"
    }
    captures_found = sum(record["lookup_status"] == "capture" for record in rows)
    failures = sum(record["lookup_status"] == "transport_failure" for record in rows)
    no_capture = sum(record["lookup_status"] == "no_capture" for record in rows)
    summary: dict[str, object] = {
        "pilot_questions": len(pilot_by_id),
        "questions_with_discovery": questions_with_discovery,
        "questions_with_captures": len(captured_question_ids),
        "urls_considered": sum(bool(record["article_url"]) for record in rows),
        "captures_found": captures_found,
        "urls_without_capture": no_capture,
        "lookup_failures": failures,
        "attempted_this_run": attempted,
        "reused_checkpoints": reused,
        "retried_failed_checkpoints": retried_failed,
        "max_urls_per_question": max_urls_per_question,
        "max_collections": max_collections,
    }
    _atomic_write_json(output / "capture-summary.json", summary)
    return summary, audit
