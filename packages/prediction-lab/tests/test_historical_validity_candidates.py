from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from prediction_lab import historical_validity_candidates as candidates
from prediction_lab.research_types import ResearchContractError


def _write_source(tmp_path: Path, rows: list[dict[str, object]]) -> tuple[Path, Path, str]:
    csv_path = tmp_path / "development.csv"
    manifest_path = tmp_path / "development.manifest.json"
    frame = pd.DataFrame(rows)
    frame.to_csv(csv_path, index=False, lineterminator="\n")
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps({"sha256": digest, "row_count": len(frame)}), encoding="utf-8"
    )
    return csv_path, manifest_path, digest


def _row(
    question_id: str,
    event_id: str,
    forecasted_at: str,
    *,
    question_text: str | None = None,
) -> dict[str, object]:
    return {
        "question_id": question_id,
        "question_text": question_text or f"Question {question_id}?",
        "forecasted_at": forecasted_at,
        "source_cutoff_at": forecasted_at,
        "event_id": event_id,
        "category": "test",
        "split": "development",
        # These columns imitate sensitive benchmark fields. Candidate selection must not load them.
        "outcome": 1,
        "market_probability": 0.99,
        "resolved_at": "2030-01-01T00:00:00Z",
    }


def _bind_synthetic_contract(
    monkeypatch: pytest.MonkeyPatch,
    *,
    digest: str,
    row_count: int,
    event_count: int,
    pilot_events: frozenset[str],
) -> None:
    monkeypatch.setattr(candidates, "SOURCE_DEVELOPMENT_SHA256", digest)
    monkeypatch.setattr(candidates, "SOURCE_DEVELOPMENT_ROWS", row_count)
    monkeypatch.setattr(candidates, "SOURCE_DEVELOPMENT_EVENT_GROUPS", event_count)
    monkeypatch.setattr(candidates, "PILOT_EVENT_IDS", pilot_events)


def test_build_fresh_candidates_excludes_pilot_and_keeps_first_event_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        _row("pilot", "event-pilot", "2026-01-01T00:00:00Z"),
        _row("later", "event-a", "2026-01-03T00:00:00Z"),
        _row(
            "early",
            "event-a",
            "2026-01-02T00:00:00Z",
            question_text="  Preserve   exact spacing?  ",
        ),
        _row("only", "event-b", "2026-01-04T00:00:00Z"),
    ]
    csv_path, manifest_path, digest = _write_source(tmp_path, rows)
    _bind_synthetic_contract(
        monkeypatch,
        digest=digest,
        row_count=4,
        event_count=3,
        pilot_events=frozenset({"event-pilot"}),
    )

    frame = candidates.build_fresh_candidates(
        development_csv=csv_path, development_manifest=manifest_path
    )

    assert frame["question_id"].tolist() == ["early", "only"]
    assert frame["event_id"].tolist() == ["event-a", "event-b"]
    assert frame.loc[0, "question_text"] == "  Preserve   exact spacing?  "
    assert tuple(frame.columns) == candidates.CANDIDATE_COLUMNS


def test_missing_frozen_pilot_event_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [_row("q1", "event-a", "2026-01-01T00:00:00Z")]
    csv_path, manifest_path, digest = _write_source(tmp_path, rows)
    _bind_synthetic_contract(
        monkeypatch,
        digest=digest,
        row_count=1,
        event_count=1,
        pilot_events=frozenset({"missing-pilot-event"}),
    )

    with pytest.raises(ResearchContractError, match="pilot event exclusions"):
        candidates.build_fresh_candidates(
            development_csv=csv_path, development_manifest=manifest_path
        )


def test_source_digest_tampering_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [_row("q1", "event-pilot", "2026-01-01T00:00:00Z")]
    csv_path, manifest_path, digest = _write_source(tmp_path, rows)
    _bind_synthetic_contract(
        monkeypatch,
        digest=digest,
        row_count=1,
        event_count=1,
        pilot_events=frozenset({"event-pilot"}),
    )
    csv_path.write_text(csv_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ResearchContractError, match="digest mismatch"):
        candidates.build_fresh_candidates(
            development_csv=csv_path, development_manifest=manifest_path
        )


def test_freeze_emits_only_preregistered_columns_and_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        _row("pilot", "event-pilot", "2026-01-01T00:00:00Z"),
        _row("q1", "event-a", "2026-01-02T00:00:00Z"),
        _row("q2", "event-b", "2026-01-03T00:00:00Z"),
    ]
    csv_path, manifest_path, digest = _write_source(tmp_path, rows)
    _bind_synthetic_contract(
        monkeypatch,
        digest=digest,
        row_count=3,
        event_count=3,
        pilot_events=frozenset({"event-pilot"}),
    )
    output_csv = tmp_path / "candidates.csv"
    output_manifest = tmp_path / "candidates.manifest.json"

    manifest = candidates.freeze_fresh_candidates(
        development_csv=csv_path,
        development_manifest=manifest_path,
        output_csv=output_csv,
        output_manifest=output_manifest,
        code_commit="a" * 40,
        source_artifact_id=123,
        source_artifact_digest="sha256:" + "b" * 64,
    )

    frozen = pd.read_csv(output_csv)
    assert tuple(frozen.columns) == candidates.CANDIDATE_COLUMNS
    assert "outcome" not in frozen.columns
    assert "market_probability" not in frozen.columns
    assert len(frozen) == 2
    assert manifest["row_count"] == 2
    assert manifest["event_group_count"] == 2
    assert manifest["retrospective_close_anchored_schedule"] is True
    assert manifest["preregistration_commit"] == candidates.PREREGISTRATION_COMMIT
    assert hashlib.sha256(output_csv.read_bytes()).hexdigest() == manifest["sha256"]
