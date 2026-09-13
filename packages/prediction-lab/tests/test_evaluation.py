from __future__ import annotations

import pandas as pd

from prediction_lab.evaluation import evaluate_forecasts


def test_report_detects_model_that_beats_market() -> None:
    frame = pd.DataFrame(
        [
            {
                "question_id": "q1",
                "question_text": "Question one?",
                "forecasted_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-01-10T00:00:00Z",
                "market_price_timestamp": "2026-01-01T00:00:00Z",
                "source_cutoff_at": "2025-12-31T23:59:00Z",
                "market_probability": 0.55,
                "model_probability": 0.80,
                "outcome": 1,
                "category": "technology",
            },
            {
                "question_id": "q2",
                "question_text": "Question two?",
                "forecasted_at": "2026-01-02T00:00:00Z",
                "resolved_at": "2026-01-20T00:00:00Z",
                "market_price_timestamp": "2026-01-02T00:00:00Z",
                "source_cutoff_at": "2026-01-01T23:59:00Z",
                "market_probability": 0.45,
                "model_probability": 0.20,
                "outcome": 0,
                "category": "technology",
            },
            {
                "question_id": "q3",
                "question_text": "Question three?",
                "forecasted_at": "2026-01-03T00:00:00Z",
                "resolved_at": "2026-02-15T00:00:00Z",
                "market_price_timestamp": "2026-01-03T00:00:00Z",
                "source_cutoff_at": "2026-01-02T23:59:00Z",
                "market_probability": 0.60,
                "model_probability": 0.75,
                "outcome": 1,
                "category": "economics",
            },
        ]
    )

    report = evaluate_forecasts(frame, calibration_bins=5)

    assert report.sample_size == 3
    assert report.model_brier < report.market_brier
    assert report.brier_delta < 0
    assert report.model_skill_vs_market > 0
    assert report.model_beats_market is True
    assert set(report.by_category) == {"technology", "economics"}
