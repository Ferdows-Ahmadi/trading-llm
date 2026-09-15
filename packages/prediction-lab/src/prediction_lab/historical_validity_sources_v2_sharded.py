"""Deterministic execution sharding for frozen historical-validity source discovery v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
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

SHARD_COUNT = 4
SHARD_SIZE = CANDIDATE_ROWS // SHARD_COUNT
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


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_parent_candidates(path: Path) -> pd.DataFrame:
    if _sha256(path.read_bytes()) != CANDIDATE_SHA256:
        raise HistoricalSourceV2Error("Frozen parent candidate CSV digest changed")
    frame = pd.read_csv(path, dtype={"question_id": str})
    if len(frame) != CANDIDATE_ROWS or tuple(frame.columns) != _ALLOWED_COLUMNS:
        raise HistoricalSourceV2Error("Frozen parent candidate artifact shape changed")
    if frame["question_id"].nunique() != CANDIDATE_ROWS:
        raise HistoricalSourceV2Error("Frozen parent candidate IDs are not unique")
    return frame


def _shard_bounds(shard_index: int) -> tuple[int, int]:
    if shard_index < 0 or shard_index >= SHARD_COUNT:
        raise HistoricalSourceV2Error(f"Shard index must be 0..{SHARD_COUNT - 1}")
    start = shard_index * SHARD_SIZE
    return start, start + SHARD_SIZE


def _write_subset_inputs(
    *,
    frame: pd.DataFrame,
    locators: dict[str, dict[str, Any]],
    shard_index: int,
    directory: Path,
) -> tuple[Path, Path, list[str], str]:
    start, end = _shard_bounds(shard_index)
    subset = frame.iloc[start:end].copy()
    question_ids = subset["question_id"].astype(str).tolist()
    if len(question_ids) != SHARD_SIZE or len(set(question_ids)) != SHARD_SIZE:
        raise HistoricalSourceV2Error("Deterministic shard membership is incomplete")

    candidates_path = directory / "candidates.csv"
    subset.to_csv(candidates_path, index=False, lineterminator="\n")
    subset_sha = _sha256(candidates_path.read_bytes())

    locators_path = directory / "locators.jsonl"
    locators_path.write_text(
        "".join(
            json.dumps(locators[question_id], ensure_ascii=False, sort_keys=True) + "\n"
            for question_id in question_ids
        ),
        encoding="utf-8",
    )
    return candidates_path, locators_path, question_ids, subset_sha


def run_shard(
    *,
    candidates_csv: Path,
    v1_locators_jsonl: Path,
    output_directory: Path,
    shard_index: int,
    code_commit: str,
) -> dict[str, object]:
    """Run one fixed contiguous 16-row execution shard under the unchanged v2 protocol."""
    frame = _load_parent_candidates(candidates_csv)
    locators = load_v1_locators(v1_locators_jsonl, expected_rows=CANDIDATE_ROWS)
    if set(frame["question_id"].astype(str)) != set(locators):
        raise HistoricalSourceV2Error("Parent candidate IDs and V1 locator IDs differ")

    output_directory.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="historical-validity-v2-shard-") as temp:
        candidates_path, locators_path, question_ids, subset_sha = _write_subset_inputs(
            frame=frame,
            locators=locators,
            shard_index=shard_index,
            directory=Path(temp),
        )
        with WaybackV2Provider() as wayback, CommonCrawlV2Provider(
            minimum_interval_seconds=0.5,
            retry_backoff_seconds=1.0,
        ) as commoncrawl:
            collections, collections_sha = commoncrawl.collections_manifest()
            summary = discover_v2_sources(
                candidates_csv=candidates_path,
                v1_locators_jsonl=locators_path,
                output_directory=output_directory,
                providers=[wayback, commoncrawl],
                code_commit=code_commit,
                candidate_sha256=subset_sha,
                expected_rows=SHARD_SIZE,
                commoncrawl_collections=collections,
                commoncrawl_collections_sha256=collections_sha,
            )

    summary.update(
        {
            "execution_mode": "deterministic-contiguous-shard",
            "parent_candidate_sha256": CANDIDATE_SHA256,
            "shard_count": SHARD_COUNT,
            "shard_index": shard_index,
            "shard_size": SHARD_SIZE,
            "subset_candidate_sha256": subset_sha,
        }
    )
    _atomic_json(output_directory / "source-discovery-v2-summary.json", summary)
    _atomic_json(
        output_directory / "shard-metadata.json",
        {
            "code_commit": code_commit,
            "parent_candidate_sha256": CANDIDATE_SHA256,
            "question_ids": question_ids,
            "shard_count": SHARD_COUNT,
            "shard_index": shard_index,
            "shard_size": SHARD_SIZE,
            "subset_candidate_sha256": subset_sha,
            "v1_artifact_digest": V1_ARTIFACT_DIGEST,
            "v2_clarification_commit": V2_CLARIFICATION_COMMIT,
            "v2_protocol_commit": V2_PROTOCOL_COMMIT,
        },
    )
    return summary


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


def _copy_content_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.iterdir()):
        if not item.is_file():
            raise HistoricalSourceV2Error("Shard content tree contains a non-file entry")
        target = destination / item.name
        if target.exists():
            if target.read_bytes() != item.read_bytes():
                raise HistoricalSourceV2Error(
                    f"Duplicate frozen content differs across shards: {item.name}"
                )
            continue
        shutil.copyfile(item, target)


def merge_shards(
    *,
    candidates_csv: Path,
    shards_root: Path,
    output_directory: Path,
    code_commit: str,
) -> dict[str, object]:
    """Verify and merge all four successful execution shards into the canonical v2 artifact."""
    frame = _load_parent_candidates(candidates_csv)
    parent_ids = frame["question_id"].astype(str).tolist()
    shard_directories = sorted(
        path
        for path in shards_root.iterdir()
        if path.is_dir()
        and path.name.startswith(
            "historical-validity-source-discovery-v0.2-shard-"
        )
    )
    if len(shard_directories) != SHARD_COUNT:
        raise HistoricalSourceV2Error("Expected exactly four successful shard artifacts")

    by_index: dict[int, Path] = {}
    collection_sha: str | None = None
    collection_bytes: bytes | None = None
    all_rows: dict[str, list[dict[str, Any]]] = {}
    seen_question_ids: set[str] = set()

    output_directory.mkdir(parents=True, exist_ok=False)
    for shard_directory in shard_directories:
        metadata = _load_json(shard_directory / "shard-metadata.json")
        summary = _load_json(shard_directory / "source-discovery-v2-summary.json")
        shard_index = metadata.get("shard_index")
        if isinstance(shard_index, bool) or not isinstance(shard_index, int):
            raise HistoricalSourceV2Error("Shard metadata has an invalid index")
        if shard_index in by_index or shard_index not in range(SHARD_COUNT):
            raise HistoricalSourceV2Error("Shard indices are duplicated or out of range")
        by_index[shard_index] = shard_directory

        if metadata.get("shard_count") != SHARD_COUNT or metadata.get("shard_size") != SHARD_SIZE:
            raise HistoricalSourceV2Error("Shard execution geometry changed")
        if metadata.get("parent_candidate_sha256") != CANDIDATE_SHA256:
            raise HistoricalSourceV2Error("Shard parent candidate identity changed")
        if metadata.get("code_commit") != code_commit or summary.get("code_commit") != code_commit:
            raise HistoricalSourceV2Error("Shard code commit differs from merge commit")
        if metadata.get("v1_artifact_digest") != V1_ARTIFACT_DIGEST:
            raise HistoricalSourceV2Error("Shard V1 artifact identity changed")
        if summary.get("commoncrawl_max_collections") != COMMON_CRAWL_MAX_COLLECTIONS:
            raise HistoricalSourceV2Error("Shard Common Crawl collection bound changed")

        expected_start, expected_end = _shard_bounds(shard_index)
        expected_ids = parent_ids[expected_start:expected_end]
        question_ids = metadata.get("question_ids")
        if question_ids != expected_ids:
            raise HistoricalSourceV2Error("Shard question membership/order changed")
        overlap = seen_question_ids & set(expected_ids)
        if overlap:
            raise HistoricalSourceV2Error("Question IDs appear in more than one shard")
        seen_question_ids.update(expected_ids)

        shard_collection_sha = summary.get("commoncrawl_collections_sha256")
        if not isinstance(shard_collection_sha, str) or not shard_collection_sha:
            raise HistoricalSourceV2Error("Shard Common Crawl manifest hash is missing")
        current_collection_bytes = (shard_directory / "commoncrawl-collections.json").read_bytes()
        if collection_sha is None:
            collection_sha = shard_collection_sha
            collection_bytes = current_collection_bytes
        elif shard_collection_sha != collection_sha or current_collection_bytes != collection_bytes:
            raise HistoricalSourceV2Error("Common Crawl collection manifest differs across shards")

        rows = _load_jsonl(shard_directory / "source-lookups-v2.jsonl")
        rows_by_id: dict[str, list[dict[str, Any]]] = {
            question_id: [] for question_id in expected_ids
        }
        seen_lookup_keys: set[tuple[object, object, object, object]] = set()
        for row in rows:
            question_id = str(row.get("question_id") or "")
            if question_id not in rows_by_id:
                raise HistoricalSourceV2Error("Shard ledger contains an out-of-shard question")
            if row.get("lookup_status") not in _ALLOWED_STATUSES:
                raise HistoricalSourceV2Error("Shard ledger contains an unknown lookup status")
            provider = row.get("provider")
            if provider is not None and provider not in _ALLOWED_PROVIDERS:
                raise HistoricalSourceV2Error("Shard ledger contains an unregistered provider")
            key = (question_id, provider, row.get("pattern"), row.get("url"))
            if key in seen_lookup_keys:
                raise HistoricalSourceV2Error("Shard ledger contains a duplicate lookup key")
            seen_lookup_keys.add(key)
            rows_by_id[question_id].append(row)
        if any(not rows_by_id[question_id] for question_id in expected_ids):
            raise HistoricalSourceV2Error("Shard ledger omitted a candidate")
        all_rows.update(rows_by_id)

        _copy_content_tree(shard_directory / "raw", output_directory / "raw")
        _copy_content_tree(shard_directory / "text", output_directory / "text")

    if set(by_index) != set(range(SHARD_COUNT)) or seen_question_ids != set(parent_ids):
        raise HistoricalSourceV2Error("Merged shard membership is incomplete")
    if collection_bytes is None or collection_sha is None:
        raise HistoricalSourceV2Error("Merged Common Crawl collection manifest is missing")

    merged_rows = [row for question_id in parent_ids for row in all_rows[question_id]]
    (output_directory / "source-lookups-v2.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in merged_rows),
        encoding="utf-8",
    )
    (output_directory / "commoncrawl-collections.json").write_bytes(collection_bytes)

    captures = sum(row["lookup_status"] == "capture" for row in merged_rows)
    transport_failures = sum(row["lookup_status"] == "transport_failure" for row in merged_rows)
    content_failures = sum(row["lookup_status"] == "content_failure" for row in merged_rows)
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
    summary: dict[str, object] = {
        "schema_version": 2,
        "purpose": "historical-validity-source-discovery-v2",
        "candidate_rows": CANDIDATE_ROWS,
        "candidate_sha256": CANDIDATE_SHA256,
        "v1_artifact_digest": V1_ARTIFACT_DIGEST,
        "v2_protocol_commit": V2_PROTOCOL_COMMIT,
        "v2_clarification_commit": V2_CLARIFICATION_COMMIT,
        "code_commit": code_commit,
        "execution_mode": "deterministic-contiguous-shards-merged",
        "shard_count": SHARD_COUNT,
        "lookup_rows": len(merged_rows),
        "captures_with_frozen_content": captures,
        "questions_with_capture": len(covered_questions),
        "transport_failures": transport_failures,
        "content_failures": content_failures,
        "no_capture": no_captures,
        "no_url": no_urls,
        "exact_question_match_diagnostics": exact_matches,
        "commoncrawl_max_collections": COMMON_CRAWL_MAX_COLLECTIONS,
        "commoncrawl_collections_sha256": collection_sha,
    }
    _atomic_json(output_directory / "source-discovery-v2-summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shard frozen historical-validity source discovery v2"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    shard = subparsers.add_parser("shard")
    shard.add_argument("candidates_csv", type=Path)
    shard.add_argument("v1_locators_jsonl", type=Path)
    shard.add_argument("output_directory", type=Path)
    shard.add_argument("--shard-index", type=int, required=True)
    shard.add_argument("--code-commit", required=True)

    merge = subparsers.add_parser("merge")
    merge.add_argument("candidates_csv", type=Path)
    merge.add_argument("shards_root", type=Path)
    merge.add_argument("output_directory", type=Path)
    merge.add_argument("--code-commit", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "shard":
        summary = run_shard(
            candidates_csv=args.candidates_csv,
            v1_locators_jsonl=args.v1_locators_jsonl,
            output_directory=args.output_directory,
            shard_index=args.shard_index,
            code_commit=args.code_commit,
        )
    else:
        summary = merge_shards(
            candidates_csv=args.candidates_csv,
            shards_root=args.shards_root,
            output_directory=args.output_directory,
            code_commit=args.code_commit,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
