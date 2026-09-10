from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

REQUIRED_COLUMNS = (
    "question_id",
    "question_text",
    "forecasted_at",
    "resolved_at",
    "market_price_timestamp",
    "source_cutoff_at",
    "market_probability",
    "model_probability",
    "outcome",
)

TIMESTAMP_COLUMNS = (
    "forecasted_at",
    "resolved_at",
    "market_price_timestamp",
    "source_cutoff_at",
)

OPTIONAL_DEFAULTS: dict[str, str] = {
    "category": "unknown",
    "model_name": "model",
    "split": "unspecified",
}


class ForecastSchemaError(ValueError):
    """Raised when forecast observations violate the evaluation data contract."""


def _require_columns(columns: Iterable[str]) -> None:
    available = set(columns)
    missing = [column for column in REQUIRED_COLUMNS if column not in available]
    if missing:
        raise ForecastSchemaError(f"Missing required columns: {', '.join(missing)}")


def normalize_forecast_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized copy of the forecast frame.

    All timestamps are converted to UTC. Probability and outcome columns are numeric.
    This function validates shape-level constraints; temporal leakage checks live in
    ``prediction_lab.leakage``.
    """

    _require_columns(frame.columns)
    normalized = frame.copy()

    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in normalized.columns:
            normalized[column] = default
        normalized[column] = normalized[column].fillna(default).astype(str)

    for column in TIMESTAMP_COLUMNS:
        try:
            normalized[column] = pd.to_datetime(normalized[column], utc=True, errors="raise")
        except (TypeError, ValueError) as exc:
            raise ForecastSchemaError(f"Invalid timestamp values in {column}") from exc
        if normalized[column].isna().any():
            bad = normalized.index[normalized[column].isna()].tolist()[:5]
            raise ForecastSchemaError(f"Null timestamps in {column} at rows {bad}")

    for column in ("market_probability", "model_probability"):
        try:
            normalized[column] = pd.to_numeric(normalized[column], errors="raise").astype(float)
        except (TypeError, ValueError) as exc:
            raise ForecastSchemaError(f"Non-numeric values in {column}") from exc
        invalid = ~normalized[column].between(0.0, 1.0, inclusive="both")
        if invalid.any():
            bad = normalized.index[invalid].tolist()[:5]
            raise ForecastSchemaError(f"{column} must be between 0 and 1 at rows {bad}")

    try:
        outcome_numeric = pd.to_numeric(normalized["outcome"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ForecastSchemaError("Outcome must contain only binary 0/1 values") from exc

    invalid_outcome = ~outcome_numeric.isin([0, 1])
    if invalid_outcome.any():
        bad = normalized.index[invalid_outcome].tolist()[:5]
        raise ForecastSchemaError(f"Outcome must be binary 0/1 at rows {bad}")
    normalized["outcome"] = outcome_numeric.astype(int)

    empty_id = normalized["question_id"].astype(str).str.strip().eq("")
    if empty_id.any():
        bad = normalized.index[empty_id].tolist()[:5]
        raise ForecastSchemaError(f"question_id cannot be empty at rows {bad}")

    normalized["question_id"] = normalized["question_id"].astype(str)
    normalized["question_text"] = normalized["question_text"].astype(str)

    return normalized
