from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

EPSILON = 1e-15


def _as_arrays(
    outcomes: Sequence[float] | np.ndarray | pd.Series,
    probabilities: Sequence[float] | np.ndarray | pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(outcomes, dtype=float)
    p = np.asarray(probabilities, dtype=float)

    if y.shape != p.shape:
        raise ValueError("outcomes and probabilities must have the same shape")
    if y.size == 0:
        raise ValueError("metrics require at least one observation")
    if not np.isin(y, [0.0, 1.0]).all():
        raise ValueError("outcomes must be binary 0/1")
    if ((p < 0.0) | (p > 1.0)).any():
        raise ValueError("probabilities must be between 0 and 1")

    return y, p


def brier_score(
    outcomes: Sequence[float] | np.ndarray | pd.Series,
    probabilities: Sequence[float] | np.ndarray | pd.Series,
) -> float:
    """Mean squared error for binary probabilistic forecasts. Lower is better."""

    y, p = _as_arrays(outcomes, probabilities)
    return float(np.mean((p - y) ** 2))


def binary_log_loss(
    outcomes: Sequence[float] | np.ndarray | pd.Series,
    probabilities: Sequence[float] | np.ndarray | pd.Series,
) -> float:
    """Binary log loss using clipping only to avoid log(0). Lower is better."""

    y, p = _as_arrays(outcomes, probabilities)
    p = np.clip(p, EPSILON, 1.0 - EPSILON)
    loss = -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))
    return float(np.mean(loss))


def brier_skill_score(model_brier: float, reference_brier: float) -> float:
    """Brier skill score versus a reference forecast.

    Positive values mean improvement over the reference. Zero means equal skill.
    Negative values mean worse skill.
    """

    if reference_brier < 0 or model_brier < 0:
        raise ValueError("Brier scores cannot be negative")
    if reference_brier == 0:
        return 0.0 if model_brier == 0 else float("-inf")
    return 1.0 - (model_brier / reference_brier)


def calibration_table(
    outcomes: Sequence[float] | np.ndarray | pd.Series,
    probabilities: Sequence[float] | np.ndarray | pd.Series,
    *,
    bins: int = 10,
) -> pd.DataFrame:
    """Build an equal-width reliability table for probabilistic forecasts."""

    if bins < 2:
        raise ValueError("bins must be at least 2")
    y, p = _as_arrays(outcomes, probabilities)

    bin_index = np.minimum((p * bins).astype(int), bins - 1)
    data = pd.DataFrame({"outcome": y, "probability": p, "bin": bin_index})

    grouped = (
        data.groupby("bin", observed=True)
        .agg(
            count=("outcome", "size"),
            mean_probability=("probability", "mean"),
            outcome_rate=("outcome", "mean"),
        )
        .reset_index()
    )
    grouped["lower_bound"] = grouped["bin"] / bins
    grouped["upper_bound"] = (grouped["bin"] + 1) / bins
    grouped["absolute_gap"] = (
        grouped["mean_probability"] - grouped["outcome_rate"]
    ).abs()

    return grouped[
        [
            "bin",
            "lower_bound",
            "upper_bound",
            "count",
            "mean_probability",
            "outcome_rate",
            "absolute_gap",
        ]
    ]


def expected_calibration_error(table: pd.DataFrame) -> float:
    """Weighted absolute calibration gap from a calibration table."""

    if table.empty:
        raise ValueError("calibration table cannot be empty")
    total = int(table["count"].sum())
    if total <= 0:
        raise ValueError("calibration table must contain observations")
    weights = table["count"] / total
    return float((weights * table["absolute_gap"]).sum())
