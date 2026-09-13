from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from prediction_lab.commoncrawl_evidence import CommonCrawlCapture, HistoricalEvidenceError
from prediction_lab.gdelt_evidence import GdeltArticle
from prediction_lab import prospective_evidence_v01 as evidence
from prediction_lab.research_types import ResearchContractError


def custody_row() -> dict[str, object]:
    return {
        "market_id": "123",
        "event_id": "event-1",
        "within_event_rank": 1,
        "question_text": "Will Example Corp launch Product X by November?",
        "description": "Resolves Yes if Product X is publicly launched before the deadline.",
        "scheduled_end_at": "2026-11-01T00:00:00Z",
        "source_cutoff_at": evidence.SOURCE_CUTOFF,
        "market_price_timestamp": "2026-09-13T19:17:20Z",
        "market_probability": 0.55,
    }


def article(*, seen_at: str = "2026-09-12T10:00:00Z") -> GdeltArticle:
    return GdeltArticle(
        title="Example Corp discusses Product X",
        url="https://news.example.com/example-product-x",
        seen_at=pd.Timestamp(seen_at),
        domain="news.example.com",
        language="English",
        source_country="US",
    )


def capture(*, timestamp: str = "2026-09-12T11:00:00Z") -> CommonCrawlCapture:
    return CommonCrawlCapture(
        crawl_id="CC-MAIN-2026-37",
        timestamp=pd.Timestamp(timestamp),
        url="https://news.example.com/example-product-x",
        digest="sha1:TESTDIGEST",
        filename="crawl-data/test.warc.gz",
        offset=100,
        length=200,
        mime="text/html",
        status="200",
    )


class FakeDiscovery:
    def __init__(self, results: list[GdeltArticle] | None = None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def search(
        self,
        question_text: str,
        *,
        cutoff: pd.Timestamp,
        lookback_days: int,
        max_records: int,
    ) -> list[GdeltArticle]:
        self.calls.append(
            {
                "question_text": question_text,
                "cutoff": cutoff,
                "lookback_days": lookback_days,
                "max_records": max_records,
            }
        )
        if self.error is not None:
            raise self.error
        return list(self.results)


class FakeArchive:
    def __init__(
        self,
        *,
        capture_value: CommonCrawlCapture | None = None,
        lookup_error: Exception | None = None,
        fetch_error: Exception | None = None,
        text: str = "Example Corp announced detailed plans for Product X. " * 20,
    ) -> None:
        self.capture_value = capture_value
        self.lookup_error = lookup_error
        self.fetch_error = fetch_error
        self.text = text
        self.lookup_calls: list[dict[str, Any]] = []
        self.fetch_calls: list[dict[str, Any]] = []

    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int,
    ) -> CommonCrawlCapture | None:
        self.lookup_calls.append(
            {"url": url, "cutoff": cutoff, "max_collections": max_collections}
        )
        if self.lookup_error is not None:
            raise self.lookup_error
        return self.capture_value

    def fetch_capture_text(
        self,
        capture_value: CommonCrawlCapture,
        *,
        max_characters: int,
    ) -> tuple[str, str]:
        self.fetch_calls.append(
            {"capture": capture_value, "max_characters": max_characters}
        )
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.text[:max_characters], "Archived Example Corp article"


def acquire(
    discovery: FakeDiscovery,
    archive: FakeArchive,
) -> dict[str, object]:
    return evidence.acquire_row(
        custody_row(),
        discovery=discovery,  # type: ignore[arg-type]
        archive=archive,  # type: ignore[arg-type]
    )


def test_canonical_problem_text_binds_frozen_schema() -> None:
    value = evidence._canonical_problem_text(custody_row())
    assert value == (
        "Market question:\nWill Example Corp launch Product X by November?\n\n"
        "Resolution criteria:\n"
        "Resolves Yes if Product X is publicly launched before the deadline.\n\n"
        "Scheduled market end:\n2026-11-01T00:00:00Z"
    )


def test_context_hash_is_deterministic_and_budget_bound() -> None:
    row = custody_row()
    first = evidence._context_hash(row)
    second = evidence._context_hash(dict(row))
    assert first == second
    assert len(first) == 64


def test_verified_complete_freezes_pre_cutoff_archived_item() -> None:
    discovery = FakeDiscovery([article()])
    archive = FakeArchive(capture_value=capture())

    record = acquire(discovery, archive)

    assert record["availability"]["status"] == "verified_complete"  # type: ignore[index]
    items = record["evidence_items"]
    assert isinstance(items, list) and len(items) == 1
    item = items[0]
    assert item["source_id"] == "gdelt-cc:CC-MAIN-2026-37:sha1:TESTDIGEST"
    assert item["available_at"] == "2026-09-12T11:00:00.000000Z"
    packet = record["evidence_packet"]
    assert packet["availability"]["status"] == "verified_complete"  # type: ignore[index]
    assert packet["research_cutoff_at"] == "2026-09-13T19:14:39.226442Z"  # type: ignore[index]
    assert discovery.calls[0]["lookback_days"] == 90
    assert discovery.calls[0]["max_records"] == 50
    assert archive.lookup_calls[0]["max_collections"] == 3
    assert archive.fetch_calls[0]["max_characters"] == 10_000


def test_no_eligible_capture_is_verified_empty() -> None:
    record = acquire(FakeDiscovery([article()]), FakeArchive(capture_value=None))

    assert record["availability"]["status"] == "verified_empty"  # type: ignore[index]
    assert record["evidence_items"] == []
    assert record["deterministic_skip_counts"] == {"no_eligible_capture": 1}


def test_successfully_fetched_but_unusable_content_is_verified_empty() -> None:
    archive = FakeArchive(
        capture_value=capture(),
        fetch_error=HistoricalEvidenceError("Archived page produced too little visible text"),
    )
    record = acquire(FakeDiscovery([article()]), archive)

    assert record["availability"]["status"] == "verified_empty"  # type: ignore[index]
    assert record["deterministic_skip_counts"] == {"content_skip": 1}
    assert record["provider_failures"] == []


def test_archive_provider_failure_is_not_relabelled_empty() -> None:
    archive = FakeArchive(
        lookup_error=HistoricalEvidenceError(
            "Common Crawl lookup exhausted with transport errors: HTTP 503"
        )
    )
    record = acquire(FakeDiscovery([article()]), archive)

    assert record["availability"]["status"] == "retrieval_failure"  # type: ignore[index]
    failures = record["provider_failures"]
    assert isinstance(failures, list) and len(failures) == 1
    assert "archive_lookup" in failures[0]


def test_gdelt_provider_failure_is_not_relabelled_empty() -> None:
    record = acquire(
        FakeDiscovery(error=HistoricalEvidenceError("GDELT request failed: timeout")),
        FakeArchive(),
    )

    assert record["availability"]["status"] == "retrieval_failure"  # type: ignore[index]
    failures = record["provider_failures"]
    assert isinstance(failures, list) and len(failures) == 1
    assert failures[0].startswith("gdelt:")


def test_post_cutoff_capture_fails_closed() -> None:
    archive = FakeArchive(
        capture_value=capture(timestamp="2026-09-14T00:00:00Z")
    )
    with pytest.raises(ResearchContractError, match="Post-cutoff evidence"):
        acquire(FakeDiscovery([article()]), archive)


def test_post_cutoff_discovery_record_fails_closed() -> None:
    archive = FakeArchive(capture_value=capture())
    with pytest.raises(ResearchContractError, match="Post-cutoff evidence"):
        acquire(
            FakeDiscovery([article(seen_at="2026-09-14T00:00:00Z")]),
            archive,
        )
