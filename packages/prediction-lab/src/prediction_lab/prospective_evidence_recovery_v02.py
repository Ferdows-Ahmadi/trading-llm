"""Transport recovery v2 for prospective clustered evidence v0.1."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import httpx

from prediction_lab import prospective_evidence_recovery_v01 as v1
from prediction_lab import prospective_evidence_v01 as base
from prediction_lab.commoncrawl_evidence import HistoricalEvidenceError
from prediction_lab.gdelt_evidence import FastCommonCrawlClient
from prediction_lab.research_types import ResearchContractError

RECOVERY_V2_AMENDMENT_COMMIT = "a4b8be56fbb7e5291c6d72c122f880609627e972"
RECOVERY_V1_RUN_ID = 34809802640
RECOVERY_V1_ARTIFACTS: dict[int, tuple[int, str]] = {
    0: (10338413642, "b59800c3cc88653362499e30e344ab63d8e5c913a41fcf9104a5e49c7578887b"),
    1: (10336931583, "13c57aaeb1f29aad7ddb71c5bd37e9b3ea8a8cdd2773f9dcae25fe55286d3be4"),
    2: (10339211930, "9da6ce9cc67b2a494dd7ccdfbd86459f57a83cb9c1597a63f4a42b9850292695"),
    3: (10339470819, "af72149ab8f4f4c198ee28c508f639d70bd8bb149c8e93f0b60404f17edaf66a"),
}
RECOVERY_V1_MERGED_ARTIFACT_ID = 10339117277
RECOVERY_V1_MERGED_ARTIFACT_SHA256 = (
    "9cf2093209106a1527af5b5cafeb9084cf2e7423fe2b812d5b4b60586c27b201"
)
RECOVERY_METHOD_VERSION = "prospective-evidence-v0.1-transport-recovery-v2"
DEFAULT_SHARD_COUNT = 4
SHARD_STAGGER_SECONDS = 30.0
GDELT_MINIMUM_INTERVAL_SECONDS = 24.0
GDELT_RETRIES = 8
GDELT_RETRY_BACKOFF_SECONDS = 5.0
COMMON_CRAWL_TIMEOUT_SECONDS = 60.0
COMMON_CRAWL_RETRIES = 8
COMMON_CRAWL_RETRY_BACKOFF_SECONDS = 2.0
COMMON_CRAWL_MINIMUM_INTERVAL_SECONDS = 1.0


class PacedFastCommonCrawlClient(FastCommonCrawlClient):
    """Fast Common Crawl client with transport-only pacing on every HTTP attempt."""

    def __init__(self, *, minimum_interval_seconds: float = 1.0, **kwargs: Any) -> None:
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds cannot be negative")
        super().__init__(**kwargs)
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_request_at: float | None = None

    def _pace(self) -> None:
        if self._last_request_at is None or self.minimum_interval_seconds == 0:
            return
        remaining = self.minimum_interval_seconds - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _get(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        last_response: httpx.Response | None = None
        for attempt in range(self.retries):
            self._pace()
            try:
                response = self._client.get(
                    url,
                    params=cast(dict[str, str | int] | None, params),
                    headers=headers,
                )
                self._last_request_at = time.monotonic()
                last_response = response
                if response.status_code != 429 and response.status_code < 500:
                    return response
            except httpx.HTTPError as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
            if attempt + 1 < self.retries:
                time.sleep(self.retry_backoff_seconds * (2**attempt))

        if last_response is not None:
            return last_response
        raise HistoricalEvidenceError(f"Common Crawl request failed: {last_error}")


def _candidate_paths(name: str, candidate_roots: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for root in candidate_roots:
        candidate = root / "checkpoints" / name
        if candidate.exists():
            paths.append(candidate)
    return paths


def assemble_seed(
    *,
    custody_zip: Path,
    candidate_roots: list[Path],
    output_directory: Path,
) -> dict[str, object]:
    """Assemble the best available pre-v2 checkpoint for every touched row."""
    rows, _ = base.load_verified_custody_archive(custody_zip)
    if output_directory.exists():
        raise ResearchContractError("Refusing to replace existing v2 seed output")
    checkpoints = output_directory / "checkpoints"
    checkpoints.mkdir(parents=True)

    status_counts: Counter[str] = Counter()
    missing_question_ids: list[str] = []
    chosen_sources: dict[str, str] = {}

    for row in rows:
        question_id = base._question_id(row)
        name = base._checkpoint_name(question_id)
        candidates = _candidate_paths(name, candidate_roots)
        if not candidates:
            missing_question_ids.append(question_id)
            continue
        source, value = v1._select_candidate(row=row, candidates=candidates)
        shutil.copy2(source, checkpoints / name)
        v1._copy_raw_for_checkpoint(
            checkpoint_name=name,
            source_root=source.parent.parent,
            destination_root=output_directory,
        )
        status_counts[v1._checkpoint_status(value)] += 1
        chosen_sources[question_id] = str(source)

    summary: dict[str, object] = {
        "schema_version": 1,
        "recovery_method_version": RECOVERY_METHOD_VERSION,
        "recovery_v2_amendment_commit": RECOVERY_V2_AMENDMENT_COMMIT,
        "recovery_v1_run_id": RECOVERY_V1_RUN_ID,
        "rows": len(rows),
        "checkpoint_rows": sum(status_counts.values()),
        "missing_rows": len(missing_question_ids),
        "missing_question_ids": missing_question_ids,
        "status_counts": dict(sorted(status_counts.items())),
        "chosen_sources": chosen_sources,
        "reserved_holdout_accessed": False,
        "model_forecast_run": False,
        "outcomes_accessed": False,
    }
    base._atomic_json(output_directory / "v2-seed-summary.json", summary)
    return summary


def run_shard_v2(
    *,
    custody_zip: Path,
    seed_root: Path,
    output_directory: Path,
    shard_index: int,
    shard_count: int,
    code_commit: str,
) -> dict[str, object]:
    if shard_count != DEFAULT_SHARD_COUNT:
        raise ResearchContractError("Recovery v2 requires the frozen four-shard assignment")
    if not 0 <= shard_index < shard_count:
        raise ResearchContractError("Invalid v2 shard index")

    delay = SHARD_STAGGER_SECONDS * shard_index
    if delay > 0:
        time.sleep(delay)

    with base.CapturingGdeltDocClient(
        minimum_interval_seconds=GDELT_MINIMUM_INTERVAL_SECONDS,
        retries=GDELT_RETRIES,
        retry_backoff_seconds=GDELT_RETRY_BACKOFF_SECONDS,
    ) as discovery, PacedFastCommonCrawlClient(
        timeout_seconds=COMMON_CRAWL_TIMEOUT_SECONDS,
        retries=COMMON_CRAWL_RETRIES,
        retry_backoff_seconds=COMMON_CRAWL_RETRY_BACKOFF_SECONDS,
        minimum_interval_seconds=COMMON_CRAWL_MINIMUM_INTERVAL_SECONDS,
    ) as archive:
        summary = v1.run_shard(
            custody_zip=custody_zip,
            seed_root=seed_root,
            output_directory=output_directory,
            shard_index=shard_index,
            shard_count=shard_count,
            code_commit=code_commit,
            discovery=discovery,
            archive=archive,
        )

    summary["recovery_method_version"] = RECOVERY_METHOD_VERSION
    summary["recovery_amendment_commit"] = RECOVERY_V2_AMENDMENT_COMMIT
    summary["seed_run_id"] = RECOVERY_V1_RUN_ID
    summary.pop("seed_artifact_id", None)
    summary.pop("seed_artifact_sha256", None)
    summary["transport"] = {
        "shard_stagger_seconds": SHARD_STAGGER_SECONDS,
        "gdelt_minimum_interval_seconds": GDELT_MINIMUM_INTERVAL_SECONDS,
        "gdelt_retries": GDELT_RETRIES,
        "gdelt_retry_backoff_seconds": GDELT_RETRY_BACKOFF_SECONDS,
        "common_crawl_timeout_seconds": COMMON_CRAWL_TIMEOUT_SECONDS,
        "common_crawl_retries": COMMON_CRAWL_RETRIES,
        "common_crawl_retry_backoff_seconds": COMMON_CRAWL_RETRY_BACKOFF_SECONDS,
        "common_crawl_minimum_interval_seconds": COMMON_CRAWL_MINIMUM_INTERVAL_SECONDS,
    }
    base._atomic_json(output_directory / "recovery-shard-summary.json", summary)
    return summary


def merge_v2(
    *,
    custody_zip: Path,
    seed_root: Path,
    shard_root: Path,
    output_directory: Path,
    code_commit: str,
) -> tuple[dict[str, object], dict[str, object] | None]:
    merge_summary = v1.merge_checkpoints(
        custody_zip=custody_zip,
        seed_root=seed_root,
        shard_root=shard_root,
        output_directory=output_directory,
    )
    merge_summary["recovery_method_version"] = RECOVERY_METHOD_VERSION
    merge_summary["recovery_amendment_commit"] = RECOVERY_V2_AMENDMENT_COMMIT
    base._atomic_json(output_directory / "recovery-merge-summary.json", merge_summary)
    if merge_summary.get("forecast_ready_candidate") is not True:
        return merge_summary, None
    final = v1.finalize_merged(
        custody_zip=custody_zip,
        merged_directory=output_directory,
        code_commit=code_commit,
    )
    return merge_summary, final


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed")
    seed.add_argument("custody_zip", type=Path)
    seed.add_argument("output_directory", type=Path)
    seed.add_argument("candidate_roots", nargs="+", type=Path)

    shard = subparsers.add_parser("shard")
    shard.add_argument("custody_zip", type=Path)
    shard.add_argument("seed_root", type=Path)
    shard.add_argument("output_directory", type=Path)
    shard.add_argument("--shard-index", type=int, required=True)
    shard.add_argument("--shard-count", type=int, default=DEFAULT_SHARD_COUNT)
    shard.add_argument("--code-commit", required=True)

    merge = subparsers.add_parser("merge")
    merge.add_argument("custody_zip", type=Path)
    merge.add_argument("seed_root", type=Path)
    merge.add_argument("shard_root", type=Path)
    merge.add_argument("output_directory", type=Path)
    merge.add_argument("--code-commit", required=True)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "seed":
        summary = assemble_seed(
            custody_zip=args.custody_zip,
            candidate_roots=args.candidate_roots,
            output_directory=args.output_directory,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    if args.command == "shard":
        summary = run_shard_v2(
            custody_zip=args.custody_zip,
            seed_root=args.seed_root,
            output_directory=args.output_directory,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            code_commit=args.code_commit,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    merge_summary, final = merge_v2(
        custody_zip=args.custody_zip,
        seed_root=args.seed_root,
        shard_root=args.shard_root,
        output_directory=args.output_directory,
        code_commit=args.code_commit,
    )
    print(json.dumps(merge_summary, indent=2, sort_keys=True))
    if final is None:
        raise SystemExit(2)
    print(json.dumps(final, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
