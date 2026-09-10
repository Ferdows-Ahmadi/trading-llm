from __future__ import annotations

import math

import pytest

from prediction_lab.metrics import (
    binary_log_loss,
    brier_score,
    brier_skill_score,
    calibration_table,
    expected_calibration_error,
)


def test_brier_score_known_values() -> None:
    outcomes = [1, 0, 1, 0]
    probabilities = [0.8, 0.3, 0.6, 0.1]
    assert brier_score(outcomes, probabilities) == pytest.approx(0.075)


def test_log_loss_prefers_better_probabilities() -> None:
    outcomes = [1, 0]
    better = binary_log_loss(outcomes, [0.9, 0.1])
    worse = binary_log_loss(outcomes, [0.6, 0.4])
    assert better < worse
    assert math.isfinite(better)


def test_brier_skill_score_positive_when_model_improves_reference() -> None:
    assert brier_skill_score(0.08, 0.10) == pytest.approx(0.2)


def test_calibration_table_preserves_observation_count() -> None:
    table = calibration_table([1, 0, 1, 0], [0.9, 0.2, 0.8, 0.1], bins=5)
    assert int(table["count"].sum()) == 4
    assert expected_calibration_error(table) >= 0
