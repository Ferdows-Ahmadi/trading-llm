from __future__ import annotations

import json
import math

import httpx
import pytest

from prediction_lab.research_types import ModelMetadata, ResearchContractError
from prediction_lab.residual_adapter import (
    MAX_ABS_LOGIT_DELTA,
    RESIDUAL_MAPPING_VERSION,
    OllamaMarketResidualAdapter,
    residual_probability,
)


def _metadata() -> ModelMetadata:
    return ModelMetadata.create(
        provider="Meta",
        model_id="Meta-Llama-3.1-8B-Instruct",
        immutable_version="sha256:" + "a" * 64,
        release_date="2024-07-23T00:00:00Z",
        knowledge_cutoff="2023-12-31T23:59:59Z",
        execution_mode="local",
        contamination_assessment="historical-safe",
        contamination_notes="Frozen historical-safe test metadata.",
    )


def _request(*source_ids: str, market_probability: float = 0.2) -> dict[str, object]:
    return {
        "evidence": {
            "evidence_items": [
                {
                    "available_at": "2025-01-01T00:00:00Z",
                    "source_id": source_id,
                    "source_type": "wayback-archived-news",
                    "text": "Historical evidence.",
                    "title": "Historical source",
                }
                for source_id in source_ids
            ]
        },
        "market_probability": market_probability,
        "mode": "market-aware",
        "question": {"question_id": "q1", "text": "Will X happen?"},
    }


def test_zero_evidence_is_exact_hard_noop_without_model_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OllamaMarketResidualAdapter(
        model="llama3.1:8b",
        metadata=_metadata(),
        client=client,
    )
    result = adapter.generate(_request(market_probability=0.37))

    assert calls == 0
    assert result["base_rate_probability"] == 0.37
    assert result["updated_probability"] == 0.37
    assert result["final_probability"] == 0.37
    assert result["cited_source_ids"] == []
    record = adapter.decision_records()["q1"]
    assert record["action"] == "hard_noop"
    assert record["evidence_strength"] == "none"
    assert record["logit_delta"] == 0.0
    assert record["hard_noop"] is True
    assert record["raw_model_output"] is None
    client.close()


def test_evidence_increase_uses_preregistered_logit_mapping() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        output = {
            "action": "increase",
            "evidence_strength": "weak",
            "confidence_or_uncertainty": "moderate uncertainty",
            "critique": "The evidence is relevant but limited.",
            "cited_source_ids": ["source-1"],
        }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(output)}},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OllamaMarketResidualAdapter(
        model="llama3.1:8b",
        metadata=_metadata(),
        client=client,
    )
    result = adapter.generate(_request("source-1", market_probability=0.2))
    expected = residual_probability(0.2, 0.25)

    assert math.isclose(result["final_probability"], expected, rel_tol=0, abs_tol=1e-15)
    assert result["base_rate_probability"] == 0.2
    record = adapter.decision_records()["q1"]
    assert record["mapping_version"] == RESIDUAL_MAPPING_VERSION
    assert record["action"] == "increase"
    assert record["evidence_strength"] == "weak"
    assert record["logit_delta"] == 0.25
    assert record["hard_noop"] is False

    body = captured["body"]
    assert isinstance(body, dict)
    schema = body["format"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert "final_probability" not in properties
    assert "updated_probability" not in properties
    citations = properties["cited_source_ids"]
    assert citations["items"] == {"type": "string", "enum": ["source-1"]}
    client.close()


def test_abstention_preserves_market_probability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        output = {
            "action": "abstain",
            "evidence_strength": "none",
            "confidence_or_uncertainty": "evidence does not justify movement",
            "critique": "The article is about the target but not decisive for the event.",
            "cited_source_ids": ["source-1"],
        }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(output)}},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OllamaMarketResidualAdapter(
        model="llama3.1:8b",
        metadata=_metadata(),
        client=client,
    )
    result = adapter.generate(_request("source-1", market_probability=0.61))

    assert result["final_probability"] == 0.61
    record = adapter.decision_records()["q1"]
    assert record["action"] == "abstain"
    assert record["logit_delta"] == 0.0
    assert record["hard_noop"] is False
    client.close()


def test_invalid_action_strength_combination_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        output = {
            "action": "increase",
            "evidence_strength": "none",
            "confidence_or_uncertainty": "invalid fixture",
            "critique": "invalid fixture",
            "cited_source_ids": ["source-1"],
        }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(output)}},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OllamaMarketResidualAdapter(
        model="llama3.1:8b",
        metadata=_metadata(),
        client=client,
    )
    with pytest.raises(ResearchContractError, match="requires non-none"):
        adapter.generate(_request("source-1"))
    client.close()


def test_duplicate_valid_citations_are_canonicalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        output = {
            "action": "decrease",
            "evidence_strength": "moderate",
            "confidence_or_uncertainty": "moderate uncertainty",
            "critique": "Evidence points down.",
            "cited_source_ids": ["source-1", "source-1", "source-2"],
        }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(output)}},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OllamaMarketResidualAdapter(
        model="llama3.1:8b",
        metadata=_metadata(),
        client=client,
    )
    result = adapter.generate(_request("source-1", "source-2"))
    assert result["cited_source_ids"] == ["source-1", "source-2"]
    assert adapter.decision_records()["q1"]["cited_source_ids"] == ["source-1", "source-2"]
    client.close()


def test_residual_probability_respects_bound_and_boundaries() -> None:
    assert residual_probability(0.0, MAX_ABS_LOGIT_DELTA) == 0.0
    assert residual_probability(1.0, -MAX_ABS_LOGIT_DELTA) == 1.0
    assert residual_probability(0.4, 0.0) == 0.4
    with pytest.raises(ResearchContractError, match="exceeds preregistered residual bound"):
        residual_probability(0.4, 0.750001)
