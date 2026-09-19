from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from prediction_lab.evaluation import evaluate_forecasts


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate prediction-market forecasts against the market baseline."
    )
    parser.add_argument("csv", type=Path, help="CSV matching the prediction-lab data contract")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the JSON report. Prints to stdout when omitted.",
    )
    parser.add_argument("--calibration-bins", type=int, default=10)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    frame = pd.read_csv(args.csv)
    report = evaluate_forecasts(frame, calibration_bins=args.calibration_bins)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
