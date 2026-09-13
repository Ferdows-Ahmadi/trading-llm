from __future__ import annotations

import numpy as np
import pandas as pd

from prediction_lab.cases import normalize_case_frame


class BaselineNotFittedError(RuntimeError):
    """Raised when a trainable baseline is used before fitting."""


class BinnedCalibrationForecaster:
    """Empirical calibration baseline trained only on development outcomes."""

    def __init__(self, *, bins: int = 10, prior_strength: float = 20.0) -> None:
        if bins < 2:
            raise ValueError("bins must be at least 2")
        if prior_strength <= 0.0:
            raise ValueError("prior_strength must be positive")

        self.bins = bins
        self.prior_strength = float(prior_strength)
        self.name = f"binned-calibration-{bins}"
        self._edges = np.linspace(0.0, 1.0, bins + 1)
        self._calibrated: np.ndarray | None = None
        self._counts: np.ndarray | None = None

    def _bin_index(self, probabilities: np.ndarray) -> np.ndarray:
        indices = np.searchsorted(self._edges, probabilities, side="right") - 1
        return np.clip(indices, 0, self.bins - 1)

    def fit(self, development_cases: pd.DataFrame) -> BinnedCalibrationForecaster:
        """Fit only from development cases; holdout labels must never be passed here."""
        normalized = normalize_case_frame(development_cases)
        if normalized.empty:
            raise ValueError("development_cases cannot be empty")

        probabilities = normalized["market_probability"].to_numpy(dtype=float)
        outcomes = normalized["outcome"].to_numpy(dtype=float)
        indices = self._bin_index(probabilities)

        counts = np.bincount(indices, minlength=self.bins).astype(float)
        wins = np.bincount(indices, weights=outcomes, minlength=self.bins).astype(float)
        centers = (self._edges[:-1] + self._edges[1:]) / 2.0

        self._counts = counts
        self._calibrated = (
            wins + self.prior_strength * centers
        ) / (counts + self.prior_strength)
        return self

    @property
    def bin_counts(self) -> np.ndarray:
        if self._counts is None:
            raise BaselineNotFittedError("BinnedCalibrationForecaster has not been fitted")
        return self._counts.copy()

    def predict(self, inputs: pd.DataFrame) -> np.ndarray:
        if self._calibrated is None:
            raise BaselineNotFittedError("BinnedCalibrationForecaster has not been fitted")
        if "market_probability" not in inputs.columns:
            raise ValueError("BinnedCalibrationForecaster requires market probability exposure")

        probabilities = inputs["market_probability"].to_numpy(dtype=float)
        if np.any(~np.isfinite(probabilities)) or np.any(
            (probabilities < 0.0) | (probabilities > 1.0)
        ):
            raise ValueError("market_probability must contain finite values in [0, 1]")

        return self._calibrated[self._bin_index(probabilities)].copy()
