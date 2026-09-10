"""Prediction-market research and evaluation primitives."""

from prediction_lab.baselines import BinnedCalibrationForecaster
from prediction_lab.evaluation import EvaluationReport, evaluate_forecasts
from prediction_lab.leakage import LeakageError, validate_no_future_information
from prediction_lab.metrics import binary_log_loss, brier_score

__all__ = [
    "BinnedCalibrationForecaster",
    "EvaluationReport",
    "LeakageError",
    "binary_log_loss",
    "brier_score",
    "evaluate_forecasts",
    "validate_no_future_information",
]
