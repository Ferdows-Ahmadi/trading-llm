"""Prediction-market research and evaluation primitives."""

from prediction_lab.evaluation import EvaluationReport, evaluate_forecasts
from prediction_lab.leakage import LeakageError, validate_no_future_information
from prediction_lab.metrics import brier_score, binary_log_loss

__all__ = [
    "EvaluationReport",
    "LeakageError",
    "binary_log_loss",
    "brier_score",
    "evaluate_forecasts",
    "validate_no_future_information",
]
