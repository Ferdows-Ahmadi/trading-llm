"""Execution-only recovery for historical-validity source-discovery v2 shard 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from prediction_lab.historical_validity_sources_v2 import (
    CANDIDATE_ROWS,
    CANDIDATE_SHA256,
    COMMON_CRAWL_MAX_COLLECTIONS,
    V1_ARTIFACT_DIGEST,
    V2_CLARIFICATION_COMMIT,
    V2_PROTOCOL_COMMIT,
    CommonCrawlV2Provider,
    HistoricalSourceV2Error,
    WaybackV2Provider,
    discover_v2_sources,
    load_v1_locators,
)
from prediction_lab.research_types import canonical_json_bytes

ACQUISITION_CODE_COMMIT = "70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2"
RECOVERY_PLAN_COMMIT = "10d32a8381c0e4453f6590858540644d17ce6c15"
ORIGINAL_RUN_ID = 34758856382
PINNED_CC_SOURCE_ARTIFACT_ID = 10318785658
PINNED_CC_SOURCE_ARTIFACT_DIGEST = (
    "sha256:9f74f8a27e2ff357d09b0dabec61b9db18eb40ffb604688650e8ac082f297ec5"
)
PINNED_CC_MANIFEST_SHA256 = (
    "9134eeb9976c3cbbbaff9830c007419dd300d5f7396b2268f4618e51441d274c"
)
ORIGINAL_SHARD_INDEX = 1
ORIGINAL_SHARD_COUNT = 4
ORIGINAL_SHARD_SIZE = 16
RECOVERY_SUBSHARD_COUNT = 16
ORIGINAL_SHARD1_START = 16
EXPECTED_SHARD1_QUESTION_IDS = (
    "716634",
    "967152",
    "973201",
    "1038582",
    "1145524",
    "1175296",
    "690700",
    "701600",
    "704075",
    "701719",
    "701576",
    "1143797",
    "701499",
    "1271641",
    "690698",
    "701766",
)
_ALLOWED_COLUMNS = (
    "question_id",
    "question_text",
    "forecasted_at",
    "source_cutoff_at",
    "event_id",
    "category",
)
_ALLOWED_STATUSES = {
    "capture",
    "no_capture",
    "transport_failure",
    "content_failure",
    "no_url",
}
_ALLOWED_PROVIDERS = {"wayback", "common-crawl"}
SUBSHARD_ARTIFACT_PREFIX = (
    "historical-validity-source-discovery-v0.2-shard-1-subshard-"
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HistoricalSourceV2Error(f"Expected JSON object: {path}")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise HistoricalSourceV2Error(f"Expected JSONL object: {path}")
        rows.append(payload)
    return rows


def _load_parent_candidates(path: Path) -> pd.DataFrame:
    if _sha256(path.read_bytes()) != CANDIDATE_SHA256:
        raise HistoricalSourceV2Error("Frozen parent candidate CSV digest changed")
    frame = pd.read_csv(path, dtype={"question_id": str})
    if len(frame) != CANDIDATE_ROWS or tuple(frame.columns) != _ALLOWED_COLUMNS:
        raise HistoricalSourceV2Error("Frozen parent candidate artifact shape changed")
    if frame["question_id"].nunique() != CANDIDATE_ROWS:
        raise HistoricalSourceV2Error("Frozen parent candidate IDs are not unique")
    observed = tuple(
        frame.iloc[
            ORIGINAL_SHARD1_START : ORIGINAL_SHARD1_START + ORIGINAL_SHARD_SIZE
        ]["question_id"].astype(str)
    )
    if observed != EXPECTED_SHARD1_QUESTION_IDS:
        raise HistoricalSourceV2Error("Frozen shard-1 membership/order changed")
    return frame


def _load_pinned_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise HistoricalSourceV2Error("Pinned Common Crawl manifest is malformed")
    digest = _sha256(canonical_json_bytes(payload))
    if digest != PINNED_CC_MANIFEST_SHA256:
        raise HistoricalSourceV2Error("Pinned Common Crawl manifest digest changed")
    return payload


class PinnedCommonCrawlV2Provider(CommonCrawlV2Provider):
    """Use the frozen original-run collection manifest with unchanged lookup logic."""

    def __init__(self, collections: list[dict[str, Any]]) -> None:
        super().__init__(minimum_interval_seconds=0.5, retry_backoff_seconds=1.0)
        self._pinned_collections = collections

    def collections(self) -> list[dict[str, Any]]:
        return self._pinned_collections


def _write_one_row_inputs(
    *,
    frame: pd.DataFrame,
    locators: dict[str, dict[str, Any]],
    recovery_subshard_index: int,
    directory: Path,
) -> tuple[Path, Path, str, str, int]:
    if recovery_subshard_index not in range(RECOVERY_SUBSHARD_COUNT):
        raise HistoricalSourceV2Error("Recovery subshard index must be 0..15")
    parent_row_index = ORIGINAL_SHARD1_START + recovery_subshard_index
    subset = frame.iloc[[parent_row_index]].copy()
    question_id = str(subset.iloc[0]["question_id"])
    expected = EXPECTED_SHARD1_QUESTION_IDS[recovery_subshard_index]
    if question_id != expected:
        raise HistoricalSourceV2Error("Recovery subshard membership changed")

    candidates_path = directory / "candidates.csv"
    subset.to_csv(candidates_path, index=False, lineterminator="\n")
    subset_sha = _sha256(candidates_path.read_bytes())

    locators_path = directory / "locators.jsonl"
    locators_path.write_text(
        json.dumps(locators[question_id], ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return candidates_path, locators_path, question_id, subset_sha, parent_row_index


def acquire_subshard(
    *,
    candidates_csv: Path,
    v1_locators_jsonl: Path,
    pinned_manifest_path: Path,
    output_directory: Path,
    recovery_subshard_index: int,
    orchestration_commit: str,
) -> dict[str, object]:
    """Acquire one original shard-1 row with frozen v2 acquisition code and inputs."""
    if output_directory.exists():
        raise HistoricalSourceV2Error("Refusing to replace an existing recovery output")
    frame = _load_parent_candidates(candidates_csv)
    locators = load_v1_locators(v1_locators_jsonl, expected_rows=CANDIDATE_ROWS)
    if set(frame["question_id"].astype(str)) != set(locators):
        raise HistoricalSourceV2Error("Parent candidate IDs and V1 locator IDs differ")
    manifest = _load_pinned_manifest(pinned_manifest_path)
    pinned_manifest_bytes = pinned_manifest_path.read_bytes()
    started_at = _utc_now()

    with tempfile.TemporaryDirectory(prefix="historical-validity-v2-recovery-") as temp:
        (
            candidates_path,
            locators_path,
            question_id,
            subset_sha,
            parent_row_index,
        ) = _write_one_row_inputs(
            frame=frame,
            locators=locators,
            recovery_subshard_index=recovery_subshard_index,
            directory=Path(temp),
        )
        with WaybackV2Provider() as wayback, PinnedCommonCrawlV2Provider(
            manifest
        ) as commoncrawl:
            summary = discover_v2_sources(
                candidates_csv=candidates_path,
                v1_locators_jsonl=locators_path,
                output_directory=output_directory,
                providers=[wayback, commoncrawl],
                code_commit=ACQUISITION_CODE_COMMIT,
                candidate_sha256=subset_sha,
                expected_rows=1,
                commoncrawl_collections=manifest,
                commoncrawl_collections_sha256=PINNED_CC_MANIFEST_SHA256,
            )

    generated_manifest = output_directory / "commoncrawl-collections.json"
    if generated_manifest.read_bytes() != pinned_manifest_bytes:
        raise HistoricalSourceV2Error("Recovery rewrote the pinned manifest differently")

    completed_at = _utc_now()
    summary.update(
        {
            "execution_mode": "single-row-shard1-recovery",
            "parent_candidate_sha256": CANDIDATE_SHA256,
            "original_shard_count": ORIGINAL_SHARD_COUNT,
            "original_shard_index": ORIGINAL_SHARD_INDEX,
            "original_shard_size": ORIGINAL_SHARD_SIZE,
            "recovery_subshard_count": RECOVERY_SUBSHARD_COUNT,
            "recovery_subshard_index": recovery_subshard_index,
            "parent_row_index": parent_row_index,
            "question_id": question_id,
            "orchestration_commit": orchestration_commit,
            "recovery_plan_commit": RECOVERY_PLAN_COMMIT,
            "acquisition_started_at": started_at,
            "acquisition_completed_at": completed_at,
            "pinned_cc_source_artifact_id": PINNED_CC_SOURCE_ARTIFACT_ID,
            "pinned_cc_source_artifact_digest": PINNED_CC_SOURCE_ARTIFACT_DIGEST,
        }
    )
    _atomic_json(output_directory / "source-discovery-v2-summary.json", summary)
    _atomic_json(
        output_directory / "recovery-subshard-metadata.json",
        {
            "acquisition_code_commit": ACQUISITION_CODE_COMMIT,
            "acquisition_started_at": started_at,
            "acquisition_completed_at": completed_at,
            "orchestration_commit": orchestration_commit,
            "parent_candidate_sha256": CANDIDATE_SHA256,
            "parent_row_index": parent_row_index,
            "pinned_cc_manifest_sha256": PINNED_CC_MANIFEST_SHA256,
            "pinned_cc_source_artifact_digest": PINNED_CC_SOURCE_ARTIFACT_DIGEST,
            "pinned_cc_source_artifact_id": PINNED_CC_SOURCE_ARTIFACT_ID,
            "question_id": question_id,
            "recovery_plan_commit": RECOVERY_PLAN_COMMIT,
            "recovery_subshard_count": RECOVERY_SUBSHARD_COUNT,
            "recovery_subshard_index": recovery_subshard_index,
            "subset_candidate_sha256": subset_sha,
            "v1_artifact_digest": V1_ARTIFACT_DIGEST,
            "v2_clarification_commit": V2_CLARIFICATION_COMMIT,
            "v2_protocol_commit": V2_PROTOCOL_COMMIT,
        },
    )
    return summary


def _copy_content_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.iterdir()):
        if not item.is_file():
            raise HistoricalSourceV2Error("Recovery content tree contains a non-file entry")
        target = destination / item.name
        if target.exists():
            if target.read_bytes() != item.read_bytes():
                raise HistoricalSourceV2Error(
                    f"Duplicate frozen content differs across subshards: {item.name}"
                )
            continue
        shutil.copyfile(item, target)


def _artifact_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("artifacts"), list):
        raise HistoricalSourceV2Error("Malformed GitHub artifact metadata")
    return [item for item in payload["artifacts"] if isinstance(item, dict)]


def _artifact_identity(
    artifacts: list[dict[str, Any]],
    *,
    name: str,
    run_id: int,
) -> dict[str, object]:
    matches = [item for item in artifacts if item.get("name") == name]
    if len(matches) != 1:
        raise HistoricalSourceV2Error(f"Expected one current-run artifact named {name}")
    item = matches[0]
    identity = item.get("id")
    digest = item.get("digest")
    workflow_run = item.get("workflow_run")
    if isinstance(identity, bool) or not isinstance(identity, int) or identity < 1:
        raise HistoricalSourceV2Error("Recovery artifact has no immutable numeric ID")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise HistoricalSourceV2Error("Recovery artifact has no SHA-256 digest")
    if item.get("expired") is not False:
        raise HistoricalSourceV2Error("Recovery artifact is expired or expiry state is unknown")
    if not isinstance(workflow_run, dict) or workflow_run.get("id") != run_id:
        raise HistoricalSourceV2Error("Recovery artifact workflow identity mismatch")
    return {
        "artifact_id": identity,
        "archive_digest": digest,
        "created_at": item.get("created_at"),
        "expires_at": item.get("expires_at"),
        "name": name,
        "workflow_run_id": run_id,
    }


def _original_shard1_subset_sha(frame: pd.DataFrame) -> str:
    subset = frame.iloc[
        ORIGINAL_SHARD1_START : ORIGINAL_SHARD1_START + ORIGINAL_SHARD_SIZE
    ].copy()
    with tempfile.TemporaryDirectory(prefix="historical-validity-shard1-hash-") as temp:
        path = Path(temp) / "candidates.csv"
        subset.to_csv(path, index=False, lineterminator="\n")
        return _sha256(path.read_bytes())


def reconstruct_shard1(
    *,
    candidates_csv: Path,
    subshards_root: Path,
    artifact_metadata_json: Path,
    pinned_manifest_path: Path,
    output_directory: Path,
    orchestration_commit: str,
    run_id: int,
) -> dict[str, object]:
    """Reconstruct original shard 1 from exactly 16 successful one-row artifacts."""
    if output_directory.exists():
        raise HistoricalSourceV2Error("Refusing to replace an existing reconstruction")
    frame = _load_parent_candidates(candidates_csv)
    pinned_manifest = _load_pinned_manifest(pinned_manifest_path)
    del pinned_manifest
    pinned_manifest_bytes = pinned_manifest_path.read_bytes()
    artifact_rows = _artifact_rows(artifact_metadata_json)
    original_subset_sha = _original_shard1_subset_sha(frame)

    output_directory.mkdir(parents=True)
    all_rows: dict[str, list[dict[str, Any]]] = {}
    seen_lookup_keys: set[tuple[object, object, object, object]] = set()
    reconstruction_artifacts: list[dict[str, object]] = []
    started_at_values: list[str] = []
    completed_at_values: list[str] = []

    for subshard_index, question_id in enumerate(EXPECTED_SHARD1_QUESTION_IDS):
        artifact_name = f"{SUBSHARD_ARTIFACT_PREFIX}{subshard_index}"
        directory = subshards_root / artifact_name
        if not directory.is_dir():
            raise HistoricalSourceV2Error(f"Missing recovery subshard directory: {artifact_name}")
        identity = _artifact_identity(
            artifact_rows,
            name=artifact_name,
            run_id=run_id,
        )
        metadata = _load_json(directory / "recovery-subshard-metadata.json")
        summary = _load_json(directory / "source-discovery-v2-summary.json")

        if metadata.get("recovery_subshard_index") != subshard_index:
            raise HistoricalSourceV2Error("Recovery subshard index changed")
        if metadata.get("question_id") != question_id:
            raise HistoricalSourceV2Error("Recovery subshard question membership changed")
        if metadata.get("parent_row_index") != ORIGINAL_SHARD1_START + subshard_index:
            raise HistoricalSourceV2Error("Recovery subshard parent-row membership changed")
        if metadata.get("acquisition_code_commit") != ACQUISITION_CODE_COMMIT:
            raise HistoricalSourceV2Error("Recovery acquisition-code commit changed")
        if metadata.get("orchestration_commit") != orchestration_commit:
            raise HistoricalSourceV2Error("Recovery orchestration commit changed")
        if metadata.get("pinned_cc_manifest_sha256") != PINNED_CC_MANIFEST_SHA256:
            raise HistoricalSourceV2Error("Recovery Common Crawl manifest identity changed")
        if summary.get("code_commit") != ACQUISITION_CODE_COMMIT:
            raise HistoricalSourceV2Error("Recovery summary acquisition-code commit changed")
        if summary.get("candidate_rows") != 1:
            raise HistoricalSourceV2Error("Recovery subshard row count changed")
        if summary.get("commoncrawl_max_collections") != COMMON_CRAWL_MAX_COLLECTIONS:
            raise HistoricalSourceV2Error("Recovery Common Crawl collection bound changed")
        if summary.get("commoncrawl_collections_sha256") != PINNED_CC_MANIFEST_SHA256:
            raise HistoricalSourceV2Error("Recovery summary Common Crawl manifest changed")
        if (directory / "commoncrawl-collections.json").read_bytes() != pinned_manifest_bytes:
            raise HistoricalSourceV2Error("Recovery subshard manifest bytes differ")

        rows = _load_jsonl(directory / "source-lookups-v2.jsonl")
        if not rows or any(str(row.get("question_id") or "") != question_id for row in rows):
            raise HistoricalSourceV2Error("Recovery subshard ledger membership changed")
        for row in rows:
            if row.get("lookup_status") not in _ALLOWED_STATUSES:
                raise HistoricalSourceV2Error("Recovery ledger has an unknown status")
            provider = row.get("provider")
            if provider is not None and provider not in _ALLOWED_PROVIDERS:
                raise HistoricalSourceV2Error("Recovery ledger has an unregistered provider")
            key = (question_id, provider, row.get("pattern"), row.get("url"))
            if key in seen_lookup_keys:
                raise HistoricalSourceV2Error("Recovery ledger has a duplicate lookup key")
            seen_lookup_keys.add(key)
        all_rows[question_id] = rows

        _copy_content_tree(directory / "raw", output_directory / "raw")
        _copy_content_tree(directory / "text", output_directory / "text")
        started_at = str(metadata.get("acquisition_started_at") or "")
        completed_at = str(metadata.get("acquisition_completed_at") or "")
        if not started_at or not completed_at:
            raise HistoricalSourceV2Error("Recovery acquisition timestamps are missing")
        started_at_values.append(started_at)
        completed_at_values.append(completed_at)
        identity.update(
            {
                "acquisition_started_at": started_at,
                "acquisition_completed_at": completed_at,
                "parent_row_index": ORIGINAL_SHARD1_START + subshard_index,
                "question_id": question_id,
                "recovery_subshard_index": subshard_index,
            }
        )
        reconstruction_artifacts.append(identity)

    merged_rows = [
        row
        for question_id in EXPECTED_SHARD1_QUESTION_IDS
        for row in all_rows[question_id]
    ]
    (output_directory / "source-lookups-v2.jsonl").write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in merged_rows
        ),
        encoding="utf-8",
    )
    (output_directory / "commoncrawl-collections.json").write_bytes(
        pinned_manifest_bytes
    )

    captures = sum(row["lookup_status"] == "capture" for row in merged_rows)
    transport_failures = sum(
        row["lookup_status"] == "transport_failure" for row in merged_rows
    )
    content_failures = sum(
        row["lookup_status"] == "content_failure" for row in merged_rows
    )
    no_captures = sum(row["lookup_status"] == "no_capture" for row in merged_rows)
    no_urls = sum(row["lookup_status"] == "no_url" for row in merged_rows)
    exact_matches = sum(
        isinstance(row.get("content"), dict)
        and row["content"].get("benchmark_question_exact_match") is True
        for row in merged_rows
    )
    covered_questions = {
        str(row["question_id"])
        for row in merged_rows
        if row["lookup_status"] == "capture"
    }
    reconstruction_summary: dict[str, object] = {
        "schema_version": 2,
        "purpose": "historical-validity-source-discovery-v2",
        "candidate_rows": ORIGINAL_SHARD_SIZE,
        "candidate_sha256": original_subset_sha,
        "v1_artifact_digest": V1_ARTIFACT_DIGEST,
        "v2_protocol_commit": V2_PROTOCOL_COMMIT,
        "v2_clarification_commit": V2_CLARIFICATION_COMMIT,
        "code_commit": ACQUISITION_CODE_COMMIT,
        "orchestration_commit": orchestration_commit,
        "recovery_plan_commit": RECOVERY_PLAN_COMMIT,
        "execution_mode": "reconstructed-from-single-row-subshards",
        "parent_candidate_sha256": CANDIDATE_SHA256,
        "shard_count": ORIGINAL_SHARD_COUNT,
        "shard_index": ORIGINAL_SHARD_INDEX,
        "shard_size": ORIGINAL_SHARD_SIZE,
        "subset_candidate_sha256": original_subset_sha,
        "recovery_subshard_count": RECOVERY_SUBSHARD_COUNT,
        "lookup_rows": len(merged_rows),
        "captures_with_frozen_content": captures,
        "questions_with_capture": len(covered_questions),
        "transport_failures": transport_failures,
        "content_failures": content_failures,
        "no_capture": no_captures,
        "no_url": no_urls,
        "exact_question_match_diagnostics": exact_matches,
        "commoncrawl_max_collections": COMMON_CRAWL_MAX_COLLECTIONS,
        "commoncrawl_collections_sha256": PINNED_CC_MANIFEST_SHA256,
        "acquisition_started_at": min(started_at_values),
        "acquisition_completed_at": max(completed_at_values),
    }
    _atomic_json(
        output_directory / "source-discovery-v2-summary.json",
        reconstruction_summary,
    )
    _atomic_json(
        output_directory / "shard-metadata.json",
        {
            "code_commit": ACQUISITION_CODE_COMMIT,
            "execution_mode": "reconstructed-from-single-row-subshards",
            "orchestration_commit": orchestration_commit,
            "parent_candidate_sha256": CANDIDATE_SHA256,
            "question_ids": list(EXPECTED_SHARD1_QUESTION_IDS),
            "recovery_plan_commit": RECOVERY_PLAN_COMMIT,
            "recovery_subshard_count": RECOVERY_SUBSHARD_COUNT,
            "shard_count": ORIGINAL_SHARD_COUNT,
            "shard_index": ORIGINAL_SHARD_INDEX,
            "shard_size": ORIGINAL_SHARD_SIZE,
            "subset_candidate_sha256": original_subset_sha,
            "v1_artifact_digest": V1_ARTIFACT_DIGEST,
            "v2_clarification_commit": V2_CLARIFICATION_COMMIT,
            "v2_protocol_commit": V2_PROTOCOL_COMMIT,
        },
    )
    _atomic_json(
        output_directory / "reconstruction-manifest.json",
        {
            "acquisition_code_commit": ACQUISITION_CODE_COMMIT,
            "orchestration_commit": orchestration_commit,
            "original_run_id": ORIGINAL_RUN_ID,
            "pinned_cc_manifest_sha256": PINNED_CC_MANIFEST_SHA256,
            "pinned_cc_source_artifact_digest": PINNED_CC_SOURCE_ARTIFACT_DIGEST,
            "pinned_cc_source_artifact_id": PINNED_CC_SOURCE_ARTIFACT_ID,
            "recovery_plan_commit": RECOVERY_PLAN_COMMIT,
            "recovery_run_id": run_id,
            "subshards": reconstruction_artifacts,
        },
    )
    return reconstruction_summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recover historical-validity v2 shard 1")
    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("candidates_csv", type=Path)
    acquire.add_argument("v1_locators_jsonl", type=Path)
    acquire.add_argument("pinned_manifest", type=Path)
    acquire.add_argument("output_directory", type=Path)
    acquire.add_argument("--subshard-index", type=int, required=True)
    acquire.add_argument("--orchestration-commit", required=True)

    reconstruct = subparsers.add_parser("reconstruct")
    reconstruct.add_argument("candidates_csv", type=Path)
    reconstruct.add_argument("subshards_root", type=Path)
    reconstruct.add_argument("artifact_metadata_json", type=Path)
    reconstruct.add_argument("pinned_manifest", type=Path)
    reconstruct.add_argument("output_directory", type=Path)
    reconstruct.add_argument("--orchestration-commit", required=True)
    reconstruct.add_argument("--run-id", type=int, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "acquire":
        summary = acquire_subshard(
            candidates_csv=args.candidates_csv,
            v1_locators_jsonl=args.v1_locators_jsonl,
            pinned_manifest_path=args.pinned_manifest,
            output_directory=args.output_directory,
            recovery_subshard_index=args.subshard_index,
            orchestration_commit=args.orchestration_commit,
        )
    else:
        summary = reconstruct_shard1(
            candidates_csv=args.candidates_csv,
            subshards_root=args.subshards_root,
            artifact_metadata_json=args.artifact_metadata_json,
            pinned_manifest_path=args.pinned_manifest,
            output_directory=args.output_directory,
            orchestration_commit=args.orchestration_commit,
            run_id=args.run_id,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
