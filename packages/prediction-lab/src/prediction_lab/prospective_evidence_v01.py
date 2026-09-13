"""Timestamp-safe evidence acquisition for prospective clustered forecaster v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx
import pandas as pd

from prediction_lab.commoncrawl_evidence import CommonCrawlCapture, HistoricalEvidenceError
from prediction_lab.gdelt_evidence import (
    FastCommonCrawlClient,
    GdeltArticle,
    GdeltDocClient,
    build_gdelt_query,
)
from prediction_lab.research_types import (
    EvidenceAvailability,
    EvidenceItem,
    EvidencePacket,
    ResearchContractError,
    content_hash,
)

REPOSITORY = "Ferdows-Ahmadi/trading-llm"
CUSTODY_RUN_ID = 34777066496
CUSTODY_ARTIFACT_ID = 10323747083
CUSTODY_ARTIFACT = "prospective-development-custody-v0.3"
CUSTODY_CODE_COMMIT = "5bf128ebddb1fe82f578072beb2028545c824553"
CUSTODY_ARCHIVE_SHA256 = (
    "01eebf244add1ff21ee8d21257a000c5ee9588f751ae456e7fc7d17c0704a6aa"
)
CUSTODY_COHORT_SHA256 = (
    "6c3cea364fd7548934a5e0e3e5a00cb45d1dd124318d9cf31ea0c012af661634"
)
CUSTODY_ROWS = 77
CUSTODY_EVENT_GROUPS = 53
SOURCE_CUTOFF = "2026-09-13T19:14:39.226442Z"
FORECASTER_PROTOCOL_COMMIT = "d6f242b78a983bcd059384a68a5c05954dfc99f2"
SCHEMA_CLARIFICATION_COMMIT = "87436e7164489a1699fec81d8cc845ceeca55012"
EVIDENCE_STATUS_CLARIFICATION_COMMIT = "cdff80cbf0fd5970799c1419f3ff08d35062729f"
METHOD_VERSION = "gdelt-commoncrawl-prospective-v1"
LOOKBACK_DAYS = 90
MAX_GDELT_RECORDS = 50
MAX_ARTICLE_URLS = 8
MAX_EVIDENCE_ITEMS = 5
MAX_COLLECTIONS = 3
MAX_CHARACTERS_PER_ITEM = 10_000


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _utc(value: object, *, field: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(str(value))
    except (TypeError, ValueError) as exc:
        raise ResearchContractError(f"Invalid {field}: {value!r}") from exc
    if pd.isna(timestamp):
        raise ResearchContractError(f"Missing {field}")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _checkpoint_name(question_id: str) -> str:
    return hashlib.sha256(question_id.encode("utf-8")).hexdigest() + ".json"


def _question_id(row: Mapping[str, object]) -> str:
    market_id = str(row.get("market_id") or "").strip()
    if not market_id:
        raise ResearchContractError("Custody row is missing market_id")
    return f"polymarket-market:{market_id}"


def _canonical_problem_text(row: Mapping[str, object]) -> str:
    question = str(row.get("question_text") or "").strip()
    description = str(row.get("description") or "").strip()
    scheduled_end = str(row.get("scheduled_end_at") or "").strip()
    if not question or not description or not scheduled_end:
        raise ResearchContractError("Custody row lacks canonical problem-statement fields")
    return (
        f"Market question:\n{question}\n\n"
        f"Resolution criteria:\n{description}\n\n"
        f"Scheduled market end:\n{scheduled_end}"
    )


def _validate_custody_rows(rows: list[dict[str, Any]], summary: Mapping[str, object]) -> None:
    if len(rows) != CUSTODY_ROWS:
        raise ResearchContractError(f"Expected {CUSTODY_ROWS} custody rows; found {len(rows)}")
    market_ids = [str(row.get("market_id") or "") for row in rows]
    if any(not value for value in market_ids) or len(set(market_ids)) != len(rows):
        raise ResearchContractError("Custody market IDs must be non-empty and unique")
    event_ids = [str(row.get("event_id") or "") for row in rows]
    if any(not value for value in event_ids) or len(set(event_ids)) != CUSTODY_EVENT_GROUPS:
        raise ResearchContractError("Custody event-cluster identity changed")
    cluster_sizes = Counter(event_ids)
    if any(size > 2 for size in cluster_sizes.values()):
        raise ResearchContractError("Custody contains more than two markets in one event cluster")
    if summary.get("cohort_sha256") != CUSTODY_COHORT_SHA256:
        raise ResearchContractError("Custody summary cohort hash changed")
    if summary.get("code_commit") != CUSTODY_CODE_COMMIT:
        raise ResearchContractError("Custody source commit changed")
    if summary.get("selected_rows") != CUSTODY_ROWS:
        raise ResearchContractError("Custody selected-row count changed")
    if summary.get("selected_event_groups") != CUSTODY_EVENT_GROUPS:
        raise ResearchContractError("Custody event-group count changed")
    if summary.get("development_forecaster_authorized") is not True:
        raise ResearchContractError("Custody does not authorize development forecasting")
    if summary.get("confirmatory_edge_claim_authorized") is not False:
        raise ResearchContractError("Custody confirmatory boundary changed")
    for row in rows:
        if str(row.get("source_cutoff_at") or "") != SOURCE_CUTOFF:
            raise ResearchContractError("Custody source cutoff changed")
        _canonical_problem_text(row)
        forecast_at = _utc(row.get("market_price_timestamp"), field="market_price_timestamp")
        cutoff_at = _utc(row.get("source_cutoff_at"), field="source_cutoff_at")
        if cutoff_at > forecast_at:
            raise ResearchContractError("Custody source cutoff is after market price timestamp")
        prior = row.get("market_probability")
        if isinstance(prior, bool) or not isinstance(prior, (int, float)):
            raise ResearchContractError("Custody market probability is not numeric")
        if not 0.0 < float(prior) < 1.0:
            raise ResearchContractError("Custody market probability is outside (0, 1)")


def load_verified_custody_archive(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = path.read_bytes()
    actual_archive = _sha256_bytes(payload)
    if actual_archive != CUSTODY_ARCHIVE_SHA256:
        raise ResearchContractError(
            f"Custody ZIP digest changed: actual={actual_archive}, expected={CUSTODY_ARCHIVE_SHA256}"
        )
    with zipfile.ZipFile(path) as archive:
        names = [item.filename for item in archive.infolist()]
        if len(names) != len(set(names)):
            raise ResearchContractError("Custody ZIP contains duplicate members")
        required = {"cohort.jsonl", "custody-summary.json"}
        if not required.issubset(names):
            raise ResearchContractError("Custody ZIP is missing required frozen members")
        cohort_bytes = archive.read("cohort.jsonl")
        if _sha256_bytes(cohort_bytes) != CUSTODY_COHORT_SHA256:
            raise ResearchContractError("Custody cohort bytes changed")
        try:
            rows = [
                json.loads(line)
                for line in cohort_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
            summary = json.loads(archive.read("custody-summary.json").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResearchContractError("Custody archive contains malformed JSON") from exc
    if not all(isinstance(row, dict) for row in rows) or not isinstance(summary, dict):
        raise ResearchContractError("Custody JSON has unexpected structure")
    typed_rows = [dict(row) for row in rows]
    _validate_custody_rows(typed_rows, summary)
    return typed_rows, dict(summary)


class CapturingGdeltDocClient(GdeltDocClient):
    """GDELT client that also freezes the provider JSON used for each search."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.last_request_params: dict[str, str | int] | None = None
        self.last_payload: dict[str, Any] | None = None

    def _request(self, params: dict[str, str | int]) -> dict[str, Any]:
        payload = super()._request(params)
        self.last_request_params = dict(params)
        self.last_payload = dict(payload)
        return payload

    def reset_capture(self) -> None:
        self.last_request_params = None
        self.last_payload = None


def _article_dict(article: GdeltArticle) -> dict[str, object]:
    return {
        "title": article.title,
        "url": article.url,
        "seen_at": article.seen_at.isoformat(),
        "domain": article.domain,
        "language": article.language,
        "source_country": article.source_country,
    }


def _is_content_skip_error(exc: HistoricalEvidenceError) -> bool:
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "could not parse common crawl warc record",
            "warc record contained no response body",
            "produced too little visible text",
        )
    )


def _context_hash(row: Mapping[str, object]) -> str:
    return content_hash(
        {
            "method_version": METHOD_VERSION,
            "question_id": _question_id(row),
            "question_text": str(row["question_text"]),
            "source_cutoff_at": str(row["source_cutoff_at"]),
            "lookback_days": LOOKBACK_DAYS,
            "max_gdelt_records": MAX_GDELT_RECORDS,
            "max_article_urls": MAX_ARTICLE_URLS,
            "max_evidence_items": MAX_EVIDENCE_ITEMS,
            "max_collections": MAX_COLLECTIONS,
            "max_characters_per_item": MAX_CHARACTERS_PER_ITEM,
            "forecaster_protocol_commit": FORECASTER_PROTOCOL_COMMIT,
            "schema_clarification_commit": SCHEMA_CLARIFICATION_COMMIT,
            "evidence_status_clarification_commit": EVIDENCE_STATUS_CLARIFICATION_COMMIT,
        }
    )


def acquire_row(
    row: Mapping[str, object],
    *,
    discovery: GdeltDocClient,
    archive: FastCommonCrawlClient,
    raw_gdelt_path: Path | None = None,
) -> dict[str, object]:
    question_id = _question_id(row)
    question_text = str(row["question_text"])
    cutoff = _utc(row["source_cutoff_at"], field="source_cutoff_at")
    forecast_at = _utc(row["market_price_timestamp"], field="market_price_timestamp")
    retrieved_at = datetime.now(UTC).isoformat()
    articles: list[GdeltArticle] = []
    provider_failures: list[str] = []
    deterministic_skips: Counter[str] = Counter()
    discovery_query: str | None = None

    if isinstance(discovery, CapturingGdeltDocClient):
        discovery.reset_capture()
    try:
        discovery_query = build_gdelt_query(question_text)
    except HistoricalEvidenceError:
        deterministic_skips["no_discovery_query_terms"] += 1
    if discovery_query is not None:
        try:
            articles = discovery.search(
                question_text,
                cutoff=cutoff,
                lookback_days=LOOKBACK_DAYS,
                max_records=MAX_GDELT_RECORDS,
            )
        except (HistoricalEvidenceError, httpx.HTTPError) as exc:
            provider_failures.append(f"gdelt:{type(exc).__name__}:{exc}")

    if raw_gdelt_path is not None and isinstance(discovery, CapturingGdeltDocClient):
        if discovery.last_payload is not None:
            _atomic_json(
                raw_gdelt_path,
                {
                    "params": discovery.last_request_params,
                    "payload": discovery.last_payload,
                },
            )

    evidence: list[EvidenceItem] = []
    seen_digests: set[str] = set()
    attempts: list[dict[str, object]] = []
    for article in articles[:MAX_ARTICLE_URLS]:
        if len(evidence) >= MAX_EVIDENCE_ITEMS:
            break
        attempt: dict[str, object] = {
            "url": article.url,
            "gdelt_seen_at": article.seen_at.isoformat(),
            "status": "started",
        }
        try:
            capture = archive.latest_capture_before(
                article.url,
                cutoff=cutoff,
                max_collections=MAX_COLLECTIONS,
            )
        except (HistoricalEvidenceError, httpx.HTTPError) as exc:
            attempt["status"] = "lookup_failure"
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            provider_failures.append(f"archive_lookup:{article.url}:{type(exc).__name__}:{exc}")
            attempts.append(attempt)
            continue
        if capture is None:
            attempt["status"] = "no_eligible_capture"
            deterministic_skips["no_eligible_capture"] += 1
            attempts.append(attempt)
            continue
        attempt["capture"] = capture.to_dict()
        if capture.digest in seen_digests:
            attempt["status"] = "duplicate_capture"
            deterministic_skips["duplicate_capture"] += 1
            attempts.append(attempt)
            continue
        if capture.timestamp > cutoff or article.seen_at > cutoff:
            raise ResearchContractError("Post-cutoff evidence escaped frozen admission rules")
        try:
            text, archived_title = archive.fetch_capture_text(
                capture,
                max_characters=MAX_CHARACTERS_PER_ITEM,
            )
        except httpx.HTTPError as exc:
            attempt["status"] = "fetch_failure"
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            provider_failures.append(f"archive_fetch:{article.url}:{type(exc).__name__}:{exc}")
            attempts.append(attempt)
            continue
        except HistoricalEvidenceError as exc:
            if _is_content_skip_error(exc):
                attempt["status"] = "content_skip"
                attempt["error"] = str(exc)
                deterministic_skips["content_skip"] += 1
                attempts.append(attempt)
                continue
            attempt["status"] = "fetch_failure"
            attempt["error"] = f"{type(exc).__name__}: {exc}"
            provider_failures.append(f"archive_fetch:{article.url}:{type(exc).__name__}:{exc}")
            attempts.append(attempt)
            continue

        available_at = max(capture.timestamp, article.seen_at)
        if available_at > cutoff:
            raise ResearchContractError("Derived evidence availability exceeds frozen cutoff")
        item = EvidenceItem.create(
            source_id=f"gdelt-cc:{capture.crawl_id}:{capture.digest}",
            source_type="gdelt-discovered-common-crawl-warc",
            uri_or_reference=(
                f"commoncrawl://{capture.crawl_id}/{capture.filename}"
                f"#{capture.offset}:{capture.length}"
            ),
            title=archived_title or article.title,
            available_at=available_at.isoformat(),
            retrieved_at=retrieved_at,
            text=text,
        )
        seen_digests.add(capture.digest)
        evidence.append(item)
        attempt["status"] = "admitted"
        attempt["source_id"] = item.source_id
        attempt["content_hash"] = item.content_hash
        attempts.append(attempt)

    if provider_failures:
        availability = EvidenceAvailability(
            "retrieval_failure",
            " | ".join(provider_failures),
        )
    elif evidence:
        availability = EvidenceAvailability(
            "verified_complete",
            "Frozen bounded GDELT/Common Crawl acquisition completed",
        )
    else:
        availability = EvidenceAvailability(
            "verified_empty",
            "Frozen bounded GDELT/Common Crawl acquisition completed with no admitted evidence",
        )

    packet = EvidencePacket.create(
        question_id=question_id,
        forecasted_at=forecast_at.isoformat(),
        research_cutoff_at=cutoff.isoformat(),
        evidence_items=evidence,
        availability=availability,
    )
    return {
        "schema_version": 1,
        "question_id": question_id,
        "market_id": str(row["market_id"]),
        "event_id": str(row["event_id"]),
        "within_event_rank": int(row["within_event_rank"]),
        "acquisition_context_hash": _context_hash(row),
        "question_text": question_text,
        "canonical_problem_text": _canonical_problem_text(row),
        "source_cutoff_at": cutoff.isoformat(),
        "forecasted_at": forecast_at.isoformat(),
        "discovery_query": discovery_query,
        "discovered_articles": [_article_dict(article) for article in articles],
        "attempted_article_urls": attempts,
        "deterministic_skip_counts": dict(sorted(deterministic_skips.items())),
        "provider_failures": provider_failures,
        "evidence_items": [item.to_dict() for item in evidence],
        "availability": availability.to_dict(),
        "evidence_packet": packet.to_dict(),
    }


def _load_checkpoint(path: Path, row: Mapping[str, object]) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResearchContractError(f"Malformed evidence checkpoint: {path}") from exc
    if not isinstance(value, dict):
        raise ResearchContractError("Evidence checkpoint must be an object")
    if value.get("question_id") != _question_id(row):
        raise ResearchContractError("Evidence checkpoint question identity mismatch")
    if value.get("acquisition_context_hash") != _context_hash(row):
        raise ResearchContractError("Evidence checkpoint context changed")
    availability = value.get("availability")
    if not isinstance(availability, dict):
        raise ResearchContractError("Evidence checkpoint lacks availability")
    status = availability.get("status")
    if status in {"verified_complete", "verified_empty"}:
        return value
    return None


def run_acquisition(
    *,
    custody_zip: Path,
    output_directory: Path,
    code_commit: str,
    discovery: GdeltDocClient,
    archive: FastCommonCrawlClient,
) -> dict[str, object]:
    rows, custody_summary = load_verified_custody_archive(custody_zip)
    output_directory.mkdir(parents=True, exist_ok=True)
    checkpoints = output_directory / "checkpoints"
    raw_gdelt = output_directory / "raw" / "gdelt"
    checkpoints.mkdir(parents=True, exist_ok=True)
    raw_gdelt.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    reused = 0
    attempted = 0
    retried_failures = 0
    for row in rows:
        question_id = _question_id(row)
        checkpoint = checkpoints / _checkpoint_name(question_id)
        existing_raw: dict[str, object] | None = None
        if checkpoint.exists():
            try:
                loaded = json.loads(checkpoint.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ResearchContractError("Malformed pre-existing evidence checkpoint") from exc
            if isinstance(loaded, dict):
                existing_raw = loaded
        reusable = _load_checkpoint(checkpoint, row)
        if reusable is not None:
            records.append(reusable)
            reused += 1
            continue
        if existing_raw is not None:
            retried_failures += 1
        attempted += 1
        record = acquire_row(
            row,
            discovery=discovery,
            archive=archive,
            raw_gdelt_path=raw_gdelt / _checkpoint_name(question_id),
        )
        _atomic_json(checkpoint, record)
        records.append(record)

    if len(records) != CUSTODY_ROWS:
        raise ResearchContractError("Evidence record count differs from frozen cohort")
    records_by_id = {str(record["question_id"]): record for record in records}
    if len(records_by_id) != CUSTODY_ROWS:
        raise ResearchContractError("Evidence question IDs are not unique")

    questions: dict[str, object] = {}
    availability: dict[str, object] = {}
    packet_lines: list[str] = []
    audit_lines: list[str] = []
    status_counts: Counter[str] = Counter()
    total_items = 0
    domains: Counter[str] = Counter()
    for row in rows:
        question_id = _question_id(row)
        record = records_by_id[question_id]
        items = record["evidence_items"]
        state = record["availability"]
        if not isinstance(items, list) or not isinstance(state, dict):
            raise ResearchContractError("Malformed final evidence record")
        questions[question_id] = items
        availability[question_id] = state
        status = str(state.get("status") or "")
        status_counts[status] += 1
        total_items += len(items)
        for article in record.get("discovered_articles", []):
            if isinstance(article, dict) and article.get("url"):
                domains[urlparse(str(article["url"])).netloc.lower()] += 1
        packet = record.get("evidence_packet")
        if not isinstance(packet, dict):
            raise ResearchContractError("Evidence record lacks packet")
        packet_lines.append(json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n")
        audit_lines.append(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    fixture = {
        "schema_version": 2,
        "questions": questions,
        "availability": availability,
    }
    fixture_path = output_directory / "evidence-fixture.json"
    fixture_bytes = (
        json.dumps(fixture, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    fixture_path.write_bytes(fixture_bytes)
    packets_path = output_directory / "evidence-packets.jsonl"
    packets_path.write_text("".join(packet_lines), encoding="utf-8")
    audit_path = output_directory / "evidence-audit.jsonl"
    audit_path.write_text("".join(audit_lines), encoding="utf-8")

    forecast_ready = set(status_counts).issubset({"verified_complete", "verified_empty"}) and sum(
        status_counts.values()
    ) == CUSTODY_ROWS
    summary: dict[str, object] = {
        "schema_version": 1,
        "method_version": METHOD_VERSION,
        "code_commit": code_commit,
        "forecaster_protocol_commit": FORECASTER_PROTOCOL_COMMIT,
        "schema_clarification_commit": SCHEMA_CLARIFICATION_COMMIT,
        "evidence_status_clarification_commit": EVIDENCE_STATUS_CLARIFICATION_COMMIT,
        "custody": {
            "run_id": CUSTODY_RUN_ID,
            "artifact_id": CUSTODY_ARTIFACT_ID,
            "artifact": CUSTODY_ARTIFACT,
            "archive_sha256": CUSTODY_ARCHIVE_SHA256,
            "cohort_sha256": CUSTODY_COHORT_SHA256,
            "snapshot_reference_at": SOURCE_CUTOFF,
            "custody_summary_code_commit": custody_summary["code_commit"],
        },
        "budgets": {
            "lookback_days": LOOKBACK_DAYS,
            "max_gdelt_records": MAX_GDELT_RECORDS,
            "max_article_urls": MAX_ARTICLE_URLS,
            "max_evidence_items": MAX_EVIDENCE_ITEMS,
            "max_collections": MAX_COLLECTIONS,
            "max_characters_per_item": MAX_CHARACTERS_PER_ITEM,
        },
        "rows": CUSTODY_ROWS,
        "event_groups": CUSTODY_EVENT_GROUPS,
        "status_counts": dict(sorted(status_counts.items())),
        "questions_with_evidence": sum(
            1 for record in records if len(record.get("evidence_items", [])) > 0
        ),
        "questions_without_evidence": sum(
            1 for record in records if len(record.get("evidence_items", [])) == 0
        ),
        "total_evidence_items": total_items,
        "attempted_this_run": attempted,
        "reused_verified_checkpoints": reused,
        "retried_failed_checkpoints": retried_failures,
        "forecast_ready": forecast_ready,
        "source_domains_discovered": dict(sorted(domains.items())),
        "evidence_fixture_sha256": _sha256_bytes(fixture_bytes),
        "evidence_packets_sha256": _sha256_bytes(packets_path.read_bytes()),
        "evidence_audit_sha256": _sha256_bytes(audit_path.read_bytes()),
        "reserved_holdout_accessed": False,
        "model_forecast_run": False,
        "outcomes_accessed": False,
    }
    _atomic_json(output_directory / "evidence-summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("custody_zip", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()

    with CapturingGdeltDocClient() as discovery, FastCommonCrawlClient() as archive:
        summary = run_acquisition(
            custody_zip=args.custody_zip,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
            discovery=discovery,
            archive=archive,
        )
    safe = {
        key: summary[key]
        for key in (
            "method_version",
            "rows",
            "event_groups",
            "status_counts",
            "questions_with_evidence",
            "questions_without_evidence",
            "total_evidence_items",
            "attempted_this_run",
            "reused_verified_checkpoints",
            "retried_failed_checkpoints",
            "forecast_ready",
            "evidence_fixture_sha256",
            "evidence_packets_sha256",
            "evidence_audit_sha256",
            "reserved_holdout_accessed",
            "model_forecast_run",
            "outcomes_accessed",
        )
    }
    print(json.dumps(safe, indent=2, sort_keys=True))
    if not summary["forecast_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
