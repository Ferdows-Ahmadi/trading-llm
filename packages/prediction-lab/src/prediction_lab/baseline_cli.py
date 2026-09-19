from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.baselines import BinnedCalibrationForecaster
from prediction_lab.datasets import verify_frozen_dataset
from prediction_lab.evaluation import evaluate_forecasts
from prediction_lab.forecasters import ConstantForecaster, MarketBaselineForecaster, run_forecaster


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate deterministic baselines on a frozen temporal holdout."
    )
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("holdout_csv", type=Path)
    parser.add_argument("holdout_manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--calibration-bins", type=int, default=10)
    parser.add_argument("--prior-strength", type=float, default=20.0)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    development = verify_frozen_dataset(
        csv_path=args.development_csv,
        manifest_path=args.development_manifest,
    )
    holdout = verify_frozen_dataset(
        csv_path=args.holdout_csv,
        manifest_path=args.holdout_manifest,
    )

    calibration = BinnedCalibrationForecaster(
        bins=args.calibration_bins,
        prior_strength=args.prior_strength,
    ).fit(development)

    forecasters = [
        MarketBaselineForecaster(),
        ConstantForecaster(),
        calibration,
    ]
    reports = {}
    for forecaster in forecasters:
        forecasts = run_forecaster(holdout, forecaster)
        reports[forecaster.name] = evaluate_forecasts(
            forecasts,
            calibration_bins=args.calibration_bins,
        ).to_dict()

    payload = {
        "development_rows": len(development),
        "holdout_rows": len(holdout),
        "calibration_bin_counts": calibration.bin_counts.astype(int).tolist(),
        "reports": reports,
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
