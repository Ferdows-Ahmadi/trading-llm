from __future__ import annotations

import json
from pathlib import Path

import pytest

from prediction_lab import prospective_evidence_recovery_v01 as recovery
from prediction_lab import prospective_evidence_v01 as base
from prediction_lab.research_types import ResearchContractError


def row(index: int) -> dict[str, object]:
    return {
        "market_id": str(1000 + index),
        "event_id": f"event-{index // 2}",
        "within_event_rank": 1 + (index % 2),
        "question_text": f"Will example {index} happen?",
        "source_cutoff_at": base.SOURCE_CUTOFF,
    }


def checkpoint_payload(item: dict[str, object], status: str, *, marker: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "question_id": base._question_id(item),
        "acquisition_context_hash": base._context_hash(item),
        "availability": {"status": status, "detail": marker},
        "marker": marker,
    }


def write_checkpoint(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_shard_rows_partition_exactly_once() -> None:
    rows = [row(index) for index in range(17)]
    partitions = [
        recovery.shard_rows(rows, shard_index=index, shard_count=4)
        for index in range(4)
    ]
    recovered_ids = [
        str(item["market_id"])
        for partition in partitions
        for item in partition
    ]

    assert sorted(recovered_ids) == sorted(str(item["market_id"]) for item in rows)
    assert len(recovered_ids) == len(set(recovered_ids)) == len(rows)
    assert [len(partition) for partition in partitions] == [5, 4, 4, 4]


def test_select_candidate_prefers_terminal_over_failure(tmp_path: Path) -> None:
    item = row(0)
    failure = tmp_path / "seed.json"
    terminal = tmp_path / "shard.json"
    write_checkpoint(
        failure,
        checkpoint_payload(item, "retrieval_failure", marker="failure"),
    )
    write_checkpoint(
        terminal,
        checkpoint_payload(item, "verified_empty", marker="terminal"),
    )

    selected_path, selected = recovery._select_candidate(
        row=item,
        candidates=[failure, terminal],
    )

    assert selected_path == terminal
    assert recovery._checkpoint_status(selected) == "verified_empty"
    assert selected["marker"] == "terminal"


def test_select_candidate_rejects_conflicting_terminal_checkpoints(tmp_path: Path) -> None:
    item = row(1)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_checkpoint(
        first,
        checkpoint_payload(item, "verified_empty", marker="first"),
    )
    write_checkpoint(
        second,
        checkpoint_payload(item, "verified_empty", marker="second"),
    )

    with pytest.raises(ResearchContractError, match="Conflicting terminal"):
        recovery._select_candidate(row=item, candidates=[first, second])


def test_select_candidate_keeps_latest_failure_when_no_terminal(tmp_path: Path) -> None:
    item = row(2)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_checkpoint(
        first,
        checkpoint_payload(item, "retrieval_failure", marker="old"),
    )
    write_checkpoint(
        second,
        checkpoint_payload(item, "retrieval_failure", marker="new"),
    )

    selected_path, selected = recovery._select_candidate(
        row=item,
        candidates=[first, second],
    )

    assert selected_path == second
    assert selected["marker"] == "new"


def test_recovery_identity_is_frozen() -> None:
    assert recovery.RECOVERY_AMENDMENT_COMMIT == (
        "08427a2b96ae62bc3549e651f98c0514c62bcfa5"
    )
    assert recovery.SEED_RUN_ID == 34779255121
    assert recovery.SEED_ARTIFACT_ID == 10326569219
    assert recovery.SEED_ARTIFACT_SHA256 == (
        "c5a634563cbd2fddb5624750b17122edb7e1d2557b0f2a6780f8329f29540268"
    )
    assert recovery.DEFAULT_SHARD_COUNT == 4
