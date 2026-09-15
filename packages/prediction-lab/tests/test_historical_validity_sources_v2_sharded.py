from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import prediction_lab.historical_validity_sources_v2_sharded as sharded
from prediction_lab.historical_validity_sources_v2 import HistoricalSourceV2Error


def _write_parent_candidates(path: Path) -> str:
    frame = pd.DataFrame(
        [
            {
                "question_id": str(index + 1),
                "question_text": f"Question {index + 1}?",
                "forecasted_at": "2025-02-01T00:00:00Z",
                "source_cutoff_at": "2025-02-01T00:00:00Z",
                "event_id": f"event-{index + 1}",
                "category": "test",
            }
            for index in range(64)
        ]
    )
    frame.to_csv(path, index=False, lineterminator="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_shard(
    root: Path,
    *,
    shard_index: int,
    code_commit: str,
    parent_sha: str,
    question_ids: list[str],
    manifest: bytes = b"[]\n",
) -> Path:
    directory = root / f"historical-validity-source-discovery-v0.2-shard-{shard_index}"
    directory.mkdir(parents=True)
    metadata = {
        "code_commit": code_commit,
        "parent_candidate_sha256": parent_sha,
        "question_ids": question_ids,
        "shard_count": 4,
        "shard_index": shard_index,
        "shard_size": 16,
        "subset_candidate_sha256": f"subset-{shard_index}",
        "v1_artifact_digest": sharded.V1_ARTIFACT_DIGEST,
        "v2_clarification_commit": sharded.V2_CLARIFICATION_COMMIT,
        "v2_protocol_commit": sharded.V2_PROTOCOL_COMMIT,
    }
    (directory / "shard-metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    summary = {
        "code_commit": code_commit,
        "commoncrawl_max_collections": 6,
        "commoncrawl_collections_sha256": "manifest-sha",
    }
    (directory / "source-discovery-v2-summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    (directory / "commoncrawl-collections.json").write_bytes(manifest)
    rows = [
        {
            "question_id": question_id,
            "event_id": f"event-{question_id}",
            "forecasted_at": "2025-02-01T00:00:00Z",
            "provider": None,
            "pattern": "no-safe-slug",
            "url": None,
            "lookup_status": "no_url",
            "capture": None,
            "content": None,
            "error": None,
        }
        for question_id in question_ids
    ]
    (directory / "source-lookups-v2.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return directory


def _build_four_shards(root: Path, *, code_commit: str, parent_sha: str) -> None:
    ids = [str(index + 1) for index in range(64)]
    for shard_index in range(4):
        start = shard_index * 16
        _write_shard(
            root,
            shard_index=shard_index,
            code_commit=code_commit,
            parent_sha=parent_sha,
            question_ids=ids[start : start + 16],
        )


def test_shard_bounds_are_frozen_contiguous_geometry() -> None:
    assert sharded._shard_bounds(0) == (0, 16)
    assert sharded._shard_bounds(3) == (48, 64)
    with pytest.raises(HistoricalSourceV2Error, match="Shard index"):
        sharded._shard_bounds(4)


def test_write_subset_inputs_preserves_parent_row_order(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.csv"
    _write_parent_candidates(candidates)
    frame = pd.read_csv(candidates, dtype={"question_id": str})
    locators = {
        str(index + 1): {
            "question_id": str(index + 1),
            "locator_status": "success",
            "locator": {"market": {"id": str(index + 1), "slug": f"m-{index + 1}"}},
        }
        for index in range(64)
    }
    subset_csv, _, question_ids, _ = sharded._write_subset_inputs(
        frame=frame,
        locators=locators,
        shard_index=2,
        directory=tmp_path,
    )
    assert question_ids == [str(index) for index in range(33, 49)]
    subset = pd.read_csv(subset_csv, dtype={"question_id": str})
    assert subset["question_id"].tolist() == question_ids


def test_merge_shards_reconstructs_all_64_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates = tmp_path / "candidates.csv"
    parent_sha = _write_parent_candidates(candidates)
    monkeypatch.setattr(sharded, "CANDIDATE_SHA256", parent_sha)
    shards = tmp_path / "shards"
    shards.mkdir()
    _build_four_shards(shards, code_commit="abc", parent_sha=parent_sha)

    summary = sharded.merge_shards(
        candidates_csv=candidates,
        shards_root=shards,
        output_directory=tmp_path / "merged",
        code_commit="abc",
    )
    assert summary["candidate_rows"] == 64
    assert summary["shard_count"] == 4
    assert summary["lookup_rows"] == 64
    assert summary["no_url"] == 64
    rows = sharded._load_jsonl(tmp_path / "merged" / "source-lookups-v2.jsonl")
    assert [row["question_id"] for row in rows] == [str(index + 1) for index in range(64)]


def test_merge_rejects_shard_membership_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates = tmp_path / "candidates.csv"
    parent_sha = _write_parent_candidates(candidates)
    monkeypatch.setattr(sharded, "CANDIDATE_SHA256", parent_sha)
    shards = tmp_path / "shards"
    shards.mkdir()
    _build_four_shards(shards, code_commit="abc", parent_sha=parent_sha)
    metadata_path = (
        shards
        / "historical-validity-source-discovery-v0.2-shard-2"
        / "shard-metadata.json"
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["question_ids"][0] = "999"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(HistoricalSourceV2Error, match="membership/order"):
        sharded.merge_shards(
            candidates_csv=candidates,
            shards_root=shards,
            output_directory=tmp_path / "merged",
            code_commit="abc",
        )
