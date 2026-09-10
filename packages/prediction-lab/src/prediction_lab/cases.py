from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from prediction_lab.leakage import validate_no_future_information
from prediction_lab.schema import normalize_forecast_frame

CASE_REQUIRED_COLUMNS = (
    "question_id",
    "question_text",
    "forecasted_at",
    "resolved_at",
    "market_price_timestamp",
    "source_cutoff_at",
    "market_probability",
    "outcome",
)


class ForecastCaseError(ValueError):
    """Raised when a forecast case violates the case data contract."""


def normalize_case_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize forecast cases before a model probability has been attached.

    The case contract contains the historical question, contemporaneous market
    probability, final outcome, and temporal cutoffs. It intentionally has no
    model forecast yet.
    """

    missing = [column for column in CASE_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ForecastCaseError(f"Missing required case columns: {', '.join(missing)}")

    staged = frame.copy()
    staged["model_probability"] = staged["market_probability"]
    staged["model_name"] = "__case_validation__"
    normalized = validate_no_future_information(staged)
    return normalized.drop(columns=["model_probability", "model_name"])


def attach_model_probabilities(
    cases: pd.DataFrame,
    probabilities: Sequence[float] | np.ndarray | pd.Series,
    *,
    model_name: str,
) -> pd.DataFrame:
    """Attach one model probability to each case and return evaluation-ready rows."""

    normalized = normalize_case_frame(cases)
    values = np.asarray(probabilities, dtype=float)

    if values.ndim != 1:
        raise ForecastCaseError("probabilities must be one-dimensional")
    if len(values) != len(normalized):
        raise ForecastCaseError(
            f"Expected {len(normalized)} probabilities, received {len(values)}"
        )
    if not model_name.strip():
        raise ForecastCaseError("model_name cannot be empty")

    with_forecast = normalized.copy()
    with_forecast["model_probability"] = values
    with_forecast["model_name"] = model_name.strip()
    return normalize_forecast_frame(with_forecast)
