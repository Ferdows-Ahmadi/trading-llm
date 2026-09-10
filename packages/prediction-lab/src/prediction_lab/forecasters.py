from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from prediction_lab.cases import attach_model_probabilities, normalize_case_frame


class Forecaster(Protocol):
    """Minimal forecasting interface for reproducible benchmark runs."""

    name: str

    def predict(self, cases: pd.DataFrame) -> np.ndarray:
        """Return one probability in [0, 1] per case."""


@dataclass(frozen=True)
class ConstantForecaster:
    """A deliberately simple reference forecaster."""

    probability: float = 0.5
    name: str = "constant-50"

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be between 0 and 1")

    def predict(self, cases: pd.DataFrame) -> np.ndarray:
        normalized = normalize_case_frame(cases)
        return np.full(len(normalized), self.probability, dtype=float)


@dataclass(frozen=True)
class MarketBaselineForecaster:
    """Copies the contemporaneous market probability exactly."""

    name: str = "market-baseline"

    def predict(self, cases: pd.DataFrame) -> np.ndarray:
        normalized = normalize_case_frame(cases)
        return normalized["market_probability"].to_numpy(dtype=float, copy=True)


def run_forecaster(cases: pd.DataFrame, forecaster: Forecaster) -> pd.DataFrame:
    """Run a forecaster and produce rows accepted by the evaluator."""

    normalized = normalize_case_frame(cases)
    probabilities = forecaster.predict(normalized)
    return attach_model_probabilities(
        normalized,
        probabilities,
        model_name=forecaster.name,
    )
