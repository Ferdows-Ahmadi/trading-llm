from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.evidence_discovery_stage import run_gdelt_discovery_stage
from prediction_lab.gdelt_evidence import GdeltDocClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run resumable GDELT discovery only, without archive retrieval."
    )
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--pilot-size", type=int, default=20)
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--max-records", type=int, default=20)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--minimum-interval-seconds", type=float, default=5.0)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    with GdeltDocClient(
        retries=args.retries,
        minimum_interval_seconds=args.minimum_interval_seconds,
    ) as discovery:
        summary, _ = run_gdelt_discovery_stage(
            development_csv=args.development_csv,
            development_manifest=args.development_manifest,
            output_directory=args.output_directory,
            discovery=discovery,
            pilot_size=args.pilot_size,
            lookback_days=args.lookback_days,
            max_records=args.max_records,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
