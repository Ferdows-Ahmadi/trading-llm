from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from prediction_lab.historical_validity_sources_v2 import HistoricalSourceV2Error
from prediction_lab.research_types import canonical_json_bytes


def _load_tool() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "historical_validity_shard1_recovery.py"
    )
    spec = importlib.util.spec_from_file_location("historical_validity_shard1_recovery", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_frame(tool: ModuleType) -> pd.DataFrame:
    ids = [f"outside-{index}" for index in range(64)]
    ids[16:32] = list(tool.EXPECTED_SHARD1_QUESTION_IDS)
    return pd.DataFrame(
        {
            "question_id": ids,
            "question_text": [f"Question {index}?" for index in range(64)],
            "forecasted_at": ["2026-01-01T00:00:00Z"] * 64,
            "source_cutoff_at": ["2026-01-01T00:00:00Z"] * 64,
            "event_id": [f"event-{index}" for index in range(64)],
            "category": ["test"] * 64,
        }
    )


def _write_parent(tool: ModuleType, tmp_path: Path) -> Path:
    path = tmp_path / "candidates.csv"
    _candidate_frame(tool).to_csv(path, index=False, lineterminator="\n")
    tool.CANDIDATE_SHA256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def _write_manifest(tool: ModuleType, tmp_path: Path) -> Path:
    manifest = [
        {
            "id": "CC-MAIN-2025-01",
            "from": "2025-01-01T00:00:00",
            "cdx-api": "https://example.test/index",
        }
    ]
    path = tmp_path / "commoncrawl-collections.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tool.PINNED_CC_MANIFEST_SHA256 = hashlib.sha256(
        canonical_json_bytes(manifest)
    ).hexdigest()
    return path


def test_frozen_recovery_membership_is_exact() -> None:
    tool = _load_tool()
    assert tool.RECOVERY_SUBSHARD_COUNT == 16
    assert len(tool.EXPECTED_SHARD1_QUESTION_IDS) == 16
    assert tool.EXPECTED_SHARD1_QUESTION_IDS[0] == "716634"
    assert tool.EXPECTED_SHARD1_QUESTION_IDS[-1] == "701766"


def test_one_row_partition_selects_only_requested_parent_row(tmp_path: Path) -> None:
    tool = _load_tool()
    frame = _candidate_frame(tool)
    locators = {
        str(question_id): {"question_id": str(question_id)}
        for question_id in frame["question_id"]
    }
    candidates, _, question_id, _, parent_row = tool._write_one_row_inputs(
        frame=frame,
        locators=locators,
        recovery_subshard_index=15,
        directory=tmp_path,
    )
    selected = pd.read_csv(candidates, dtype={"question_id": str})
    assert len(selected) == 1
    assert question_id == "701766"
    assert parent_row == 31
    assert selected.iloc[0]["question_id"] == "701766"


def test_pinned_manifest_rejects_drift(tmp_path: Path) -> None:
    tool = _load_tool()
    path = tmp_path / "commoncrawl-collections.json"
    path.write_text("[]\n", encoding="utf-8")
    with pytest.raises(HistoricalSourceV2Error, match="manifest digest changed"):
        tool._load_pinned_manifest(path)


def test_reconstruction_restores_original_shard_shape(tmp_path: Path) -> None:
    tool = _load_tool()
    parent = _write_parent(tool, tmp_path)
    manifest_path = _write_manifest(tool, tmp_path)
    manifest_bytes = manifest_path.read_bytes()
    subshards = tmp_path / "subshards"
    subshards.mkdir()
    artifacts: list[dict[str, object]] = []
    orchestration_commit = "orchestration-test"
    run_id = 12345

    for index, question_id in enumerate(tool.EXPECTED_SHARD1_QUESTION_IDS):
        name = f"{tool.SUBSHARD_ARTIFACT_PREFIX}{index}"
        directory = subshards / name
        directory.mkdir()
        (directory / "commoncrawl-collections.json").write_bytes(manifest_bytes)
        (directory / "source-lookups-v2.jsonl").write_text(
            json.dumps(
                {
                    "question_id": question_id,
                    "event_id": f"event-{16 + index}",
                    "forecasted_at": "2026-01-01T00:00:00Z",
                    "provider": "wayback",
                    "pattern": "test",
                    "url": f"https://example.test/{question_id}",
                    "lookup_status": "no_capture",
                    "capture": None,
                    "content": None,
                    "error": None,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        metadata = {
            "acquisition_code_commit": tool.ACQUISITION_CODE_COMMIT,
            "acquisition_started_at": f"2026-09-13T00:{index:02d}:00+00:00",
            "acquisition_completed_at": f"2026-09-13T00:{index:02d}:30+00:00",
            "orchestration_commit": orchestration_commit,
            "parent_row_index": 16 + index,
            "pinned_cc_manifest_sha256": tool.PINNED_CC_MANIFEST_SHA256,
            "question_id": question_id,
            "recovery_subshard_index": index,
        }
        (directory / "recovery-subshard-metadata.json").write_text(
            json.dumps(metadata),
            encoding="utf-8",
        )
        summary = {
            "candidate_rows": 1,
            "code_commit": tool.ACQUISITION_CODE_COMMIT,
            "commoncrawl_max_collections": tool.COMMON_CRAWL_MAX_COLLECTIONS,
            "commoncrawl_collections_sha256": tool.PINNED_CC_MANIFEST_SHA256,
        }
        (directory / "source-discovery-v2-summary.json").write_text(
            json.dumps(summary),
            encoding="utf-8",
        )
        artifacts.append(
            {
                "id": 1000 + index,
                "name": name,
                "digest": "sha256:" + f"{index + 1:064x}",
                "expired": False,
                "created_at": "2026-09-13T00:00:00Z",
                "expires_at": "2026-12-12T00:00:00Z",
                "workflow_run": {"id": run_id},
            }
        )

    artifact_metadata = tmp_path / "artifacts.json"
    artifact_metadata.write_text(
        json.dumps({"artifacts": artifacts}),
        encoding="utf-8",
    )
    output = tmp_path / "reconstructed"
    summary = tool.reconstruct_shard1(
        candidates_csv=parent,
        subshards_root=subshards,
        artifact_metadata_json=artifact_metadata,
        pinned_manifest_path=manifest_path,
        output_directory=output,
        orchestration_commit=orchestration_commit,
        run_id=run_id,
    )

    metadata = json.loads((output / "shard-metadata.json").read_text())
    ledger = [
        json.loads(line)
        for line in (output / "source-lookups-v2.jsonl").read_text().splitlines()
    ]
    reconstruction = json.loads((output / "reconstruction-manifest.json").read_text())
    assert summary["candidate_rows"] == 16
    assert summary["shard_index"] == 1
    assert metadata["question_ids"] == list(tool.EXPECTED_SHARD1_QUESTION_IDS)
    assert [row["question_id"] for row in ledger] == list(
        tool.EXPECTED_SHARD1_QUESTION_IDS
    )
    assert len(reconstruction["subshards"]) == 16
