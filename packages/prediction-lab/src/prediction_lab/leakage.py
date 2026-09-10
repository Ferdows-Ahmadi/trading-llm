from __future__ import annotations

import pandas as pd

from prediction_lab.schema import normalize_forecast_frame


class LeakageError(ValueError):
    """Raised when observations use information unavailable at forecast time."""


def _rows(mask: pd.Series) -> list[int | str]:
    return mask.index[mask].tolist()[:5]


def validate_no_future_information(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the core temporal invariants for historical forecasting.

    The market price and every research source must be timestamped no later than the
    forecast itself. The event must resolve strictly after the forecast. Duplicate
    observations for the same model/question/timestamp are rejected.

    Returns a normalized copy so callers can safely continue evaluation.
    """

    normalized = normalize_forecast_frame(frame)

    future_market_price = normalized["market_price_timestamp"] > normalized["forecasted_at"]
    if future_market_price.any():
        raise LeakageError(
            "Market prices from the future detected at rows "
            f"{_rows(future_market_price)}"
        )

    future_source = normalized["source_cutoff_at"] > normalized["forecasted_at"]
    if future_source.any():
        raise LeakageError(
            "Research sources newer than the forecast detected at rows "
            f"{_rows(future_source)}"
        )

    already_resolved = normalized["resolved_at"] <= normalized["forecasted_at"]
    if already_resolved.any():
        raise LeakageError(
            "Forecasts made at or after resolution detected at rows "
            f"{_rows(already_resolved)}"
        )

    duplicate_mask = normalized.duplicated(
        subset=["question_id", "forecasted_at", "model_name"],
        keep=False,
    )
    if duplicate_mask.any():
        raise LeakageError(
            "Duplicate question/model/timestamp observations detected at rows "
            f"{_rows(duplicate_mask)}"
        )

    return normalized


def validate_temporal_holdout(
    train_frame: pd.DataFrame,
    test_frame: pd.DataFrame,
) -> None:
    """Require the test period to begin strictly after the training period ends."""

    train = normalize_forecast_frame(train_frame)
    test = normalize_forecast_frame(test_frame)

    if train.empty or test.empty:
        raise LeakageError("Temporal holdout validation requires non-empty train and test data")

    train_end = train["forecasted_at"].max()
    test_start = test["forecasted_at"].min()
    if test_start <= train_end:
        raise LeakageError(
            "Temporal holdout overlaps training data: "
            f"train_end={train_end.isoformat()}, test_start={test_start.isoformat()}"
        )
