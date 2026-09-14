"""Transport-only sharded recovery for prospective clustered evidence v0.1."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from prediction_lab import prospective_evidence_v01 as base
from prediction_lab.gdelt_evidence import FastCommonCrawlClient
from prediction_lab.research_types import ResearchContractError

RECOVERY_AMENDMENT_COMMIT = "08427a2b96ae62bc3549e651f98c0514c62bcfa5"
SEED_RUN_ID = 34779255121
SEED_ARTIFACT_ID = 10326569219
SEED_ARTIFACT_SHA256 = (
    "c5a634563cbd2fddb5624750b17122edb7e1d2557b0f2a6780f8329f29540268"
)
DEFAULT_SHARD_COUNT = 4
RECOVERY_METHOD_VERSION = "prospective-evidence-v0.1-transport-recovery-v1"


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _checkpoint_status(value: Mapping[str, object]) -> str:
    availability = value.get("availability")
    if not isinstance(availability, Mapping):
        raise ResearchContractError("Recovery checkpoint lacks availability")
    status = availability.get("status")
    if not isinstance(status, str) or not status:
        raise ResearchContractError("Recovery checkpoint has invalid availability status")
    return status


def _load_candidate(path: Path, row: Mapping[str, object]) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchContractError(f"Cannot read recovery checkpoint: {path}") from exc
    if not isinstance(value, dict):
        raise ResearchContractError("Recovery checkpoint must be a JSON object")
    if value.get("question_id") != base._question_id(row):
        raise ResearchContractError("Recovery checkpoint question identity mismatch")
    if value.get("acquisition_context_hash") != base._context_hash(row):
        raise ResearchContractError("Recovery checkpoint context changed")
    _checkpoint_status(value)
    return value


def shard_rows(
    rows: list[dict[str, Any]],
    *,
    shard_index: int,
    shard_count: int,
) -> list[dict[str, Any]]:
    if shard_count < 1:
        raise ResearchContractError("shard_count must be positive")
    if not 0 <= shard_index < shard_count:
        raise ResearchContractError("shard_index must be within [0, shard_count)")
    return [row for index, row in enumerate(rows) if index % shard_count == shard_index]


def _copy_raw_for_checkpoint(
    *,
    checkpoint_name: str,
    source_root: Path,
    destination_root: Path,
) -> None:
    source = source_root / "raw" / "gdelt" / checkpoint_name
    if not source.exists():
        return
    destination = destination_root / "raw" / "gdelt" / checkpoint_name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def run_shard(
    *,
    custody_zip: Path,
    seed_root: Path,
    output_directory: Path,
    shard_index: int,
    shard_count: int,
    code_commit: str,
    discovery: base.CapturingGdeltDocClient,
    archive: FastCommonCrawlClient,
) -> dict[str, object]:
    rows, _ = base.load_verified_custody_archive(custody_zip)
    selected = shard_rows(rows, shard_index=shard_index, shard_count=shard_count)
    if output_directory.exists():
        raise ResearchContractError("Refusing to replace existing recovery shard output")
    checkpoints = output_directory / "checkpoints"
    raw_gdelt = output_directory / "raw" / "gdelt"
    checkpoints.mkdir(parents=True)
    raw_gdelt.mkdir(parents=True)

    status_counts: Counter[str] = Counter()
    reused_terminal = 0
    retried_failures = 0
    new_attempts = 0
    question_ids: list[str] = []

    for row in selected:
        question_id = base._question_id(row)
        question_ids.append(question_id)
        name = base._checkpoint_name(question_id)
        seed_checkpoint = seed_root / "checkpoints" / name
        if seed_checkpoint.exists():
            seed_value = _load_candidate(seed_checkpoint, row)
            seed_status = _checkpoint_status(seed_value)
            if seed_status in {"verified_complete", "verified_empty"}:
                shutil.copy2(seed_checkpoint, checkpoints / name)
                _copy_raw_for_checkpoint(
                    checkpoint_name=name,
                    source_root=seed_root,
                    destination_root=output_directory,
                )
                status_counts[seed_status] += 1
                reused_terminal += 1
                continue
            if seed_status == "retrieval_failure":
                retried_failures += 1
            else:
                raise ResearchContractError(
                    f"Unexpected seed checkpoint status: {seed_status!r}"
                )
        else:
            new_attempts += 1

        record = base.acquire_row(
            row,
            discovery=discovery,
            archive=archive,
            raw_gdelt_path=raw_gdelt / name,
        )
        base._atomic_json(checkpoints / name, record)
        status_counts[_checkpoint_status(record)] += 1

    if len(question_ids) != len(set(question_ids)):
        raise ResearchContractError("Shard question IDs are not unique")
    if sum(status_counts.values()) != len(selected):
        raise ResearchContractError("Shard status accounting is incomplete")

    digest = hashlib.sha256()
    for path in sorted(checkpoints.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    summary: dict[str, object] = {
        "schema_version": 1,
        "recovery_method_version": RECOVERY_METHOD_VERSION,
        "recovery_amendment_commit": RECOVERY_AMENDMENT_COMMIT,
        "code_commit": code_commit,
        "seed_run_id": SEED_RUN_ID,
        "seed_artifact_id": SEED_ARTIFACT_ID,
        "seed_artifact_sha256": SEED_ARTIFACT_SHA256,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "selected_rows": len(selected),
        "question_ids": question_ids,
        "status_counts": dict(sorted(status_counts.items())),
        "reused_terminal_checkpoints": reused_terminal,
        "retried_failed_checkpoints": retried_failures,
        "new_attempts": new_attempts,
        "checkpoint_set_sha256": digest.hexdigest(),
        "reserved_holdout_accessed": False,
        "model_forecast_run": False,
        "outcomes_accessed": False,
    }
    _atomic_json(output_directory / "recovery-shard-summary.json", summary)
    return summary


def _candidate_paths(name: str, seed_root: Path, shard_root: Path) -> list[Path]:
    paths: list[Path] = []
    seed = seed_root / "checkpoints" / name
    if seed.exists():
        paths.append(seed)
    for path in sorted(shard_root.glob(f"**/checkpoints/{name}")):
        if path not in paths:
            paths.append(path)
    return paths


def _select_candidate(
    *,
    row: Mapping[str, object],
    candidates: list[Path],
) -> tuple[Path, dict[str, object]]:
    if not candidates:
        raise ResearchContractError(
            f"No recovery checkpoint exists for {base._question_id(row)}"
        )
    parsed = [(path, _load_candidate(path, row)) for path in candidates]
    terminals = [
        pair
        for pair in parsed
        if _checkpoint_status(pair[1]) in {"verified_complete", "verified_empty"}
    ]
    if terminals:
        canonical = json.dumps(
            terminals[0][1],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for _, value in terminals[1:]:
            other = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if other != canonical:
                raise ResearchContractError("Conflicting terminal recovery checkpoints")
        return terminals[0]
    return parsed[-1]


def merge_checkpoints(
    *,
    custody_zip: Path,
    seed_root: Path,
    shard_root: Path,
    output_directory: Path,
) -> dict[str, object]:
    rows, _ = base.load_verified_custody_archive(custody_zip)
    if output_directory.exists():
        raise ResearchContractError("Refusing to replace existing merged recovery output")
    checkpoints = output_directory / "checkpoints"
    checkpoints.mkdir(parents=True)

    status_counts: Counter[str] = Counter()
    chosen_sources: dict[str, str] = {}
    for row in rows:
        question_id = base._question_id(row)
        name = base._checkpoint_name(question_id)
        source, value = _select_candidate(
            row=row,
            candidates=_candidate_paths(name, seed_root, shard_root),
        )
        shutil.copy2(source, checkpoints / name)
        _copy_raw_for_checkpoint(
            checkpoint_name=name,
            source_root=source.parent.parent,
            destination_root=output_directory,
        )
        status_counts[_checkpoint_status(value)] += 1
        chosen_sources[question_id] = str(source)

    terminal = status_counts["verified_complete"] + status_counts["verified_empty"]
    merge_summary: dict[str, object] = {
        "schema_version": 1,
        "recovery_method_version": RECOVERY_METHOD_VERSION,
        "recovery_amendment_commit": RECOVERY_AMENDMENT_COMMIT,
        "rows": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "terminal_rows": terminal,
        "nonterminal_rows": len(rows) - terminal,
        "chosen_sources": chosen_sources,
        "forecast_ready_candidate": terminal == len(rows),
        "reserved_holdout_accessed": False,
        "model_forecast_run": False,
        "outcomes_accessed": False,
    }
    _atomic_json(output_directory / "recovery-merge-summary.json", merge_summary)
    return merge_summary


class _ForbiddenProvider:
    def __getattr__(self, name: str) -> object:
        raise ResearchContractError(
            f"Finalization attempted forbidden provider access via {name!r}"
        )


def finalize_merged(
    *,
    custody_zip: Path,
    merged_directory: Path,
    code_commit: str,
) -> dict[str, object]:
    merge_summary = json.loads(
        (merged_directory / "recovery-merge-summary.json").read_text(encoding="utf-8")
    )
    if not isinstance(merge_summary, dict):
        raise ResearchContractError("Malformed recovery merge summary")
    if merge_summary.get("forecast_ready_candidate") is not True:
        raise ResearchContractError(
            "Recovery merge still contains nonterminal evidence checkpoints"
        )
    summary = base.run_acquisition(
        custody_zip=custody_zip,
        output_directory=merged_directory,
        code_commit=code_commit,
        discovery=_ForbiddenProvider(),  # type: ignore[arg-type]
        archive=_ForbiddenProvider(),  # type: ignore[arg-type]
    )
    if summary.get("forecast_ready") is not True:
        raise ResearchContractError("Finalized recovery artifact is not forecast-ready")
    if summary.get("attempted_this_run") != 0:
        raise ResearchContractError("Finalization unexpectedly attempted provider access")
    if summary.get("reused_verified_checkpoints") != base.CUSTODY_ROWS:
        raise ResearchContractError("Finalization did not reuse all terminal checkpoints")
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    shard = subparsers.add_parser("shard")
    shard.add_argument("custody_zip", type=Path)
    shard.add_argument("seed_root", type=Path)
    shard.add_argument("output_directory", type=Path)
    shard.add_argument("--shard-index", type=int, required=True)
    shard.add_argument("--shard-count", type=int, default=DEFAULT_SHARD_COUNT)
    shard.add_argument("--code-commit", required=True)
    shard.add_argument("--gdelt-minimum-interval-seconds", type=float, default=20.0)

    merge = subparsers.add_parser("merge")
    merge.add_argument("custody_zip", type=Path)
    merge.add_argument("seed_root", type=Path)
    merge.add_argument("shard_root", type=Path)
    merge.add_argument("output_directory", type=Path)
    merge.add_argument("--code-commit", required=True)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "shard":
        with base.CapturingGdeltDocClient(
            minimum_interval_seconds=args.gdelt_minimum_interval_seconds,
        ) as discovery, FastCommonCrawlClient() as archive:
            summary = run_shard(
                custody_zip=args.custody_zip,
                seed_root=args.seed_root,
                output_directory=args.output_directory,
                shard_index=args.shard_index,
                shard_count=args.shard_count,
                code_commit=args.code_commit,
                discovery=discovery,
                archive=archive,
            )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    merge_summary = merge_checkpoints(
        custody_zip=args.custody_zip,
        seed_root=args.seed_root,
        shard_root=args.shard_root,
        output_directory=args.output_directory,
    )
    print(json.dumps(merge_summary, indent=2, sort_keys=True))
    if merge_summary.get("forecast_ready_candidate") is not True:
        raise SystemExit(2)
    final = finalize_merged(
        custody_zip=args.custody_zip,
        merged_directory=args.output_directory,
        code_commit=args.code_commit,
    )
    print(json.dumps(final, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
