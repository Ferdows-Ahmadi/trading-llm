from __future__ import annotations

import json

import httpx
import pytest

from prediction_lab.ollama_adapter import OllamaStructuredModelAdapter
from prediction_lab.research_types import ModelMetadata, ResearchContractError


def _metadata(*, immutable_version: str) -> ModelMetadata:
    return ModelMetadata.create(
        provider="Meta",
        model_id="Meta-Llama-3.1-8B-Instruct",
        immutable_version=immutable_version,
        release_date="2024-07-23T00:00:00Z",
        knowledge_cutoff="2023-12-31T23:59:59Z",
        execution_mode="local",
        contamination_assessment="historical-safe",
        contamination_notes=(
            "Official model card states December 2023 knowledge cutoff; machine cutoff uses "
            "month-end as a conservative upper bound. Local artifact digest is frozen."
        ),
    )


def test_ollama_adapter_posts_strict_structured_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        output = {
            "base_rate_probability": 0.4,
            "updated_probability": 0.6,
            "final_probability": 0.55,
            "confidence_or_uncertainty": "moderate uncertainty",
            "critique": "Evidence is sparse.",
            "cited_source_ids": ["source-1"],
        }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(output)}},
            request=request,
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    )
    adapter = OllamaStructuredModelAdapter(
        model="llama3.1:8b",
        metadata=_metadata(immutable_version="sha256:" + "a" * 64),
        client=http_client,
    )
    result = adapter.generate(
        {
            "evidence": {"evidence_items": []},
            "mode": "blind",
            "question": {"question_id": "q1", "text": "Will X happen?"},
        }
    )

    assert result["final_probability"] == 0.55
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["stream"] is False
    assert body["options"] == {"seed": 0, "temperature": 0}
    assert isinstance(body["format"], dict)
    assert body["format"]["additionalProperties"] is False
    messages = body["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    http_client.close()


def test_ollama_adapter_requires_frozen_sha256_artifact() -> None:
    with pytest.raises(ResearchContractError, match="immutable_version"):
        OllamaStructuredModelAdapter(
            model="llama3.1:8b",
            metadata=_metadata(immutable_version="llama3.1:8b"),
        )


def test_ollama_adapter_rejects_non_json_content() -> None:
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": "not json"}},
                request=request,
            )
        )
    )
    adapter = OllamaStructuredModelAdapter(
        model="llama3.1:8b",
        metadata=_metadata(immutable_version="sha256:" + "b" * 64),
        client=http_client,
    )
    with pytest.raises(ResearchContractError, match="not valid JSON"):
        adapter.generate({"question": {"question_id": "q1"}})
    http_client.close()
