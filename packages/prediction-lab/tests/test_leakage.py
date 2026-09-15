from __future__ import annotations

import pandas as pd
import pytest

from prediction_lab.leakage import (
    LeakageError,
    validate_no_future_information,
    validate_temporal_holdout,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "question_id": "q1",
                "question_text": "Will event one happen?",
                "forecasted_at": "2026-01-10T12:00:00Z",
                "resolved_at": "2026-01-20T00:00:00Z",
                "market_price_timestamp": "2026-01-10T11:59:00Z",
                "source_cutoff_at": "2026-01-10T11:55:00Z",
                "market_probability": 0.55,
                "model_probability": 0.65,
                "outcome": 1,
                "model_name": "baseline",
            }
        ]
    )


def test_valid_temporal_record_passes() -> None:
    normalized = validate_no_future_information(_frame())
    assert str(normalized["forecasted_at"].dtype) == "datetime64[ns, UTC]"


def test_future_source_is_rejected() -> None:
    frame = _frame()
    frame.loc[0, "source_cutoff_at"] = "2026-01-10T12:01:00Z"

    with pytest.raises(LeakageError, match="Research sources newer"):
        validate_no_future_information(frame)


def test_future_market_price_is_rejected() -> None:
    frame = _frame()
    frame.loc[0, "market_price_timestamp"] = "2026-01-10T12:00:01Z"

    with pytest.raises(LeakageError, match="Market prices from the future"):
        validate_no_future_information(frame)


def test_temporal_holdout_rejects_overlap() -> None:
    train = _frame()
    test = _frame()
    test.loc[0, "question_id"] = "q2"
    test.loc[0, "forecasted_at"] = "2026-01-09T12:00:00Z"
    test.loc[0, "market_price_timestamp"] = "2026-01-09T11:59:00Z"
    test.loc[0, "source_cutoff_at"] = "2026-01-09T11:55:00Z"

    with pytest.raises(LeakageError, match="overlaps training data"):
        validate_temporal_holdout(train, test)
