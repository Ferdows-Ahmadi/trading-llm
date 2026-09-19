from __future__ import annotations

import pandas as pd
import pytest

from prediction_lab.baselines import BaselineNotFittedError, BinnedCalibrationForecaster
from prediction_lab.evaluation import evaluate_forecasts
from prediction_lab.forecasters import MarketBaselineForecaster, run_forecaster


def _cases() -> pd.DataFrame:
    rows = []
    outcomes = [0, 0, 0, 1, 1, 1, 1, 1]
    probabilities = [0.15, 0.20, 0.25, 0.35, 0.65, 0.70, 0.75, 0.85]
    for index, (probability, outcome) in enumerate(zip(probabilities, outcomes, strict=True)):
        rows.append(
            {
                "question_id": f"q{index}",
                "question_text": f"Question {index}?",
                "forecasted_at": f"2025-01-{index + 1:02d}T00:00:00Z",
                "resolved_at": "2025-03-01T00:00:00Z",
                "market_price_timestamp": f"2025-01-{index + 1:02d}T00:00:00Z",
                "source_cutoff_at": f"2025-01-{index + 1:02d}T00:00:00Z",
                "market_probability": probability,
                "outcome": outcome,
                "category": "test",
                "platform": "kalshi",
            }
        )
    return pd.DataFrame(rows)


def test_market_baseline_is_exact_control() -> None:
    forecasts = run_forecaster(_cases(), MarketBaselineForecaster())
    report = evaluate_forecasts(forecasts)
    assert report.brier_delta == pytest.approx(0.0)
    assert report.model_skill_vs_market == pytest.approx(0.0)
    assert report.model_beats_market is False


def test_binned_calibration_must_be_fitted() -> None:
    model = BinnedCalibrationForecaster(bins=4)
    with pytest.raises(BaselineNotFittedError):
        model.predict(pd.DataFrame({"market_probability": [0.5]}))


def test_binned_calibration_learns_from_development_only() -> None:
    development = _cases()
    model = BinnedCalibrationForecaster(bins=4, prior_strength=2.0).fit(development)
    inputs = pd.DataFrame({"market_probability": [0.20, 0.80]})
    predictions = model.predict(inputs)

    assert predictions[0] < 0.20
    assert predictions[1] > 0.80
    assert model.bin_counts.sum() == len(development)
