from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.benchmark import (
    PINNED_JON_BECKER_REVISION,
    build_kalshi_cases_from_parquet,
    choose_temporal_holdout_start,
)
from prediction_lab.datasets import freeze_cases, temporal_question_split


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a leakage-safe Kalshi benchmark from prediction-market-analysis "
            "Parquet data."
        )
    )
    parser.add_argument(
        "source_root",
        type=Path,
        help="Extracted upstream data directory containing kalshi/markets and kalshi/trades.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/prediction-lab/benchmark-v0.1"),
    )
    parser.add_argument("--minimum-lead", default="7D")
    parser.add_argument("--min-volume", type=int, default=100)
    parser.add_argument("--max-questions", type=int, default=1000)
    parser.add_argument("--holdout-fraction", type=float, default=0.25)
    parser.add_argument("--source-revision", default=PINNED_JON_BECKER_REVISION)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    cases = build_kalshi_cases_from_parquet(
        args.source_root,
        minimum_lead=args.minimum_lead,
        min_volume=args.min_volume,
        max_questions=args.max_questions,
    )
    holdout_start = choose_temporal_holdout_start(
        cases,
        holdout_fraction=args.holdout_fraction,
    )
    development, holdout = temporal_question_split(cases, holdout_start=holdout_start)

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    selection_policy = (
        f"kalshi latest trade >= {args.minimum_lead} before conservative resolution boundary; "
        f"min_volume={args.min_volume}; max_questions={args.max_questions}; "
        f"holdout_fraction={args.holdout_fraction}; holdout_start={holdout_start.isoformat()}"
    )

    manifests = {}
    for name, frame in (("development", development), ("holdout", holdout)):
        manifest = freeze_cases(
            frame,
            csv_path=output / f"{name}.csv",
            manifest_path=output / f"{name}.manifest.json",
            source_name="Jon-Becker/prediction-market-analysis",
            source_revision=args.source_revision,
            selection_policy=selection_policy,
        )
        manifests[name] = manifest.to_dict()

    summary = {
        "source_revision": args.source_revision,
        "minimum_lead": args.minimum_lead,
        "holdout_start": holdout_start.isoformat(),
        "development_rows": len(development),
        "holdout_rows": len(holdout),
        "manifests": manifests,
    }
    (output / "benchmark-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
