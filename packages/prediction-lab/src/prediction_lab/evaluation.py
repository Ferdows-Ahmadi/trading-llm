from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from prediction_lab.leakage import validate_no_future_information
from prediction_lab.metrics import (
    binary_log_loss,
    brier_score,
    brier_skill_score,
    calibration_table,
    expected_calibration_error,
)


@dataclass(frozen=True)
class SliceMetrics:
    sample_size: int
    model_brier: float
    market_brier: float
    brier_delta: float
    model_skill_vs_market: float


@dataclass(frozen=True)
class EvaluationReport:
    sample_size: int
    model_brier: float
    market_brier: float
    brier_delta: float
    model_skill_vs_market: float
    model_log_loss: float
    market_log_loss: float
    model_ece: float
    market_ece: float
    per_observation_win_rate: float
    model_beats_market: bool
    by_category: dict[str, SliceMetrics]
    by_market_probability_bucket: dict[str, SliceMetrics]
    by_horizon_bucket: dict[str, SliceMetrics]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _slice_metrics(frame: pd.DataFrame) -> SliceMetrics:
    outcomes = frame["outcome"]
    model = frame["model_probability"]
    market = frame["market_probability"]
    model_brier = brier_score(outcomes, model)
    market_brier = brier_score(outcomes, market)
    return SliceMetrics(
        sample_size=len(frame),
        model_brier=model_brier,
        market_brier=market_brier,
        brier_delta=model_brier - market_brier,
        model_skill_vs_market=brier_skill_score(model_brier, market_brier),
    )


def _group_metrics(frame: pd.DataFrame, group_column: str) -> dict[str, SliceMetrics]:
    result: dict[str, SliceMetrics] = {}
    for key, group in frame.groupby(group_column, observed=True, dropna=False):
        result[str(key)] = _slice_metrics(group)
    return result


def evaluate_forecasts(frame: pd.DataFrame, *, calibration_bins: int = 10) -> EvaluationReport:
    """Compare model probabilities with contemporaneous market probabilities.

    ``brier_delta`` is model Brier minus market Brier, so negative values are better.
    A positive ``model_skill_vs_market`` also means the model beat the market baseline.
    """

    normalized = validate_no_future_information(frame)
    if normalized.empty:
        raise ValueError("evaluation requires at least one forecast")

    outcomes = normalized["outcome"]
    model = normalized["model_probability"]
    market = normalized["market_probability"]

    model_brier = brier_score(outcomes, model)
    market_brier = brier_score(outcomes, market)
    model_log = binary_log_loss(outcomes, model)
    market_log = binary_log_loss(outcomes, market)

    model_calibration = calibration_table(outcomes, model, bins=calibration_bins)
    market_calibration = calibration_table(outcomes, market, bins=calibration_bins)

    normalized = normalized.copy()
    normalized["_model_brier_loss"] = (model - outcomes) ** 2
    normalized["_market_brier_loss"] = (market - outcomes) ** 2
    normalized["_model_wins"] = normalized["_model_brier_loss"] < normalized["_market_brier_loss"]

    normalized["_market_probability_bucket"] = pd.cut(
        normalized["market_probability"],
        bins=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        include_lowest=True,
        labels=["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"],
    )

    horizon_days = (
        normalized["resolved_at"] - normalized["forecasted_at"]
    ).dt.total_seconds() / 86400.0
    normalized["_horizon_bucket"] = pd.cut(
        horizon_days,
        bins=[0.0, 1.0, 7.0, 30.0, 90.0, 365.0, np.inf],
        include_lowest=True,
        labels=["<=1d", "1-7d", "7-30d", "30-90d", "90-365d", ">365d"],
    )

    return EvaluationReport(
        sample_size=len(normalized),
        model_brier=model_brier,
        market_brier=market_brier,
        brier_delta=model_brier - market_brier,
        model_skill_vs_market=brier_skill_score(model_brier, market_brier),
        model_log_loss=model_log,
        market_log_loss=market_log,
        model_ece=expected_calibration_error(model_calibration),
        market_ece=expected_calibration_error(market_calibration),
        per_observation_win_rate=float(normalized["_model_wins"].mean()),
        model_beats_market=model_brier < market_brier,
        by_category=_group_metrics(normalized, "category"),
        by_market_probability_bucket=_group_metrics(
            normalized.dropna(subset=["_market_probability_bucket"]),
            "_market_probability_bucket",
        ),
        by_horizon_bucket=_group_metrics(
            normalized.dropna(subset=["_horizon_bucket"]),
            "_horizon_bucket",
        ),
    )
