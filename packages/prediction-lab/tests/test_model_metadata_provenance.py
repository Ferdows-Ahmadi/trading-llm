from __future__ import annotations

import pytest

from prediction_lab.research_types import ModelMetadata, ResearchContractError


def _metadata(*, knowledge_cutoff: object | None) -> ModelMetadata:
    return ModelMetadata.create(
        provider="fixture",
        model_id="fixture-model",
        immutable_version="fixture-v1",
        release_date="2020-01-01T00:00:00Z",
        knowledge_cutoff=knowledge_cutoff,
        execution_mode="api",
        contamination_assessment="historical-safe",
        contamination_notes="Fixture metadata for provenance contract tests.",
    )


def test_unknown_knowledge_cutoff_round_trips_as_json_null() -> None:
    metadata = _metadata(knowledge_cutoff=None)
    payload = metadata.to_dict()

    assert payload["knowledge_cutoff"] is None
    restored = ModelMetadata.from_dict(payload)
    assert restored == metadata
    assert restored.knowledge_cutoff is None


def test_unknown_knowledge_cutoff_fails_closed_for_historical_scoring() -> None:
    metadata = _metadata(knowledge_cutoff=None)

    with pytest.raises(ResearchContractError, match="known model knowledge cutoff"):
        metadata.assert_safe_for_historical_scoring("2025-01-01T00:00:00Z")


def test_known_pre_forecast_knowledge_cutoff_remains_historical_safe() -> None:
    metadata = _metadata(knowledge_cutoff="2020-06-01T00:00:00Z")

    metadata.assert_safe_for_historical_scoring("2025-01-01T00:00:00Z")
