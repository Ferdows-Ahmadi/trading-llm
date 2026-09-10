from __future__ import annotations

import pandas as pd
import pytest

from prediction_lab.cases import attach_model_probabilities
from prediction_lab.evaluation import evaluate_forecasts
from prediction_lab.forecasters import MarketBaselineForecaster, run_forecaster


def _cases() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "question_id": "q1",
                "question_text": "Will A happen?",
                "forecasted_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-01-10T00:00:00Z",
                "market_price_timestamp": "2026-01-01T00:00:00Z",
                "source_cutoff_at": "2026-01-01T00:00:00Z",
                "market_probability": 0.60,
                "outcome": 1,
                "category": "technology",
            },
            {
                "question_id": "q2",
                "question_text": "Will B happen?",
                "forecasted_at": "2026-01-02T00:00:00Z",
                "resolved_at": "2026-01-15T00:00:00Z",
                "market_price_timestamp": "2026-01-02T00:00:00Z",
                "source_cutoff_at": "2026-01-02T00:00:00Z",
                "market_probability": 0.30,
                "outcome": 0,
                "category": "economics",
            },
        ]
    )


def test_market_forecaster_is_exact_reference() -> None:
    forecasts = run_forecaster(_cases(), MarketBaselineForecaster())
    report = evaluate_forecasts(forecasts)
    assert report.brier_delta == pytest.approx(0.0)
    assert report.model_skill_vs_market == pytest.approx(0.0)


def test_attach_model_probabilities_preserves_case_contract() -> None:
    forecasts = attach_model_probabilities(
        _cases(),
        [0.7, 0.2],
        model_name="test-model",
    )
    assert forecasts["model_name"].tolist() == ["test-model", "test-model"]
    assert forecasts["model_probability"].tolist() == [0.7, 0.2]
