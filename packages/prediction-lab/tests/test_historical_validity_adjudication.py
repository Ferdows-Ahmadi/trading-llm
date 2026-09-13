from __future__ import annotations

import json
from pathlib import Path

import pytest

from prediction_lab.historical_validity_adjudication import (
    A_VERIFIED,
    AuditError,
    CANDIDATE_SHA,
    PROTOCOL_COMMIT,
    SOURCE_DIGEST,
    SOURCE_ID,
    adjudicate_b,
    adjudicate_c,
    load_evidence,
    overall,
    unknown_bc,
)


def test_overall_classification_is_mechanical() -> None:
    assert overall("verified", "verified", "verified") == "verified_valid"
    assert overall("unknown", "verified", "verified") == "unknown"
    assert overall("verified", "contradicted", "verified") == "invalid"


def test_b_status_must_match_event_ordering() -> None:
    result = adjudicate_b(
        "2026-01-30T09:51:18Z",
        {
            "status": "verified",
            "decisive_event_at": "2026-02-05T00:00:00Z",
            "timestamp_precision": "date",
            "sources": [],
        },
    )
    assert result["status"] == "verified"
    with pytest.raises(AuditError):
        adjudicate_b(
            "2026-01-30T09:51:18Z",
            {
                "status": "verified",
                "decisive_event_at": "2026-01-20T00:00:00Z",
                "sources": [],
            },
        )


def test_c_status_is_derived_from_canonical_label() -> None:
    yes = adjudicate_c(
        1,
        {"status": "verified", "authoritative_outcome": "Yes", "sources": []},
    )
    assert yes["status"] == "verified"
    with pytest.raises(AuditError):
        adjudicate_c(
            0,
            {"status": "verified", "authoritative_outcome": "Yes", "sources": []},
        )


def test_unknown_contract_terms_keep_b_and_c_unknown() -> None:
    b, c = unknown_bc(1)
    assert b["status"] == "unknown"
    assert c["status"] == "unknown"
    assert c["canonical_outcome"] == "Yes"


def test_manual_evidence_is_bound_to_exact_three_cases(tmp_path: Path) -> None:
    payload = {
        "protocol_commit": PROTOCOL_COMMIT,
        "candidate_sha256": CANDIDATE_SHA,
        "source_discovery_artifact_id": SOURCE_ID,
        "source_discovery_artifact_digest": SOURCE_DIGEST,
        "cases": {question_id: {} for question_id in sorted(A_VERIFIED)},
    }
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert set(load_evidence(path)) == A_VERIFIED
    payload["cases"].pop(next(iter(payload["cases"])))
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AuditError):
        load_evidence(path)
