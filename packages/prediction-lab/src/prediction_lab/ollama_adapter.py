from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping

import httpx

from prediction_lab.research_types import (
    ModelMetadata,
    ResearchContractError,
    canonical_json_bytes,
)

_IMMUTABLE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

STRUCTURED_FORECAST_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "base_rate_probability": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "updated_probability": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "final_probability": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "confidence_or_uncertainty": {
            "type": "string",
            "minLength": 1,
        },
        "critique": {
            "type": "string",
            "minLength": 1,
        },
        "cited_source_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
    },
    "required": [
        "base_rate_probability",
        "updated_probability",
        "final_probability",
        "confidence_or_uncertainty",
        "critique",
        "cited_source_ids",
    ],
}

_SYSTEM_PROMPT = """You are a historical probabilistic forecaster.
Use only the question and evidence supplied in the user payload.
Do not claim access to tools, the internet, later events, or hidden outcomes.
Follow the requested stages internally, then return exactly one JSON object matching the schema.
Probabilities must be numbers between 0 and 1. Cite only source IDs present in the evidence payload.
When evidence is weak or absent, express that uncertainty in the probability and critique.
"""


def _allowed_source_ids(request: Mapping[str, object]) -> tuple[str, ...]:
    evidence = request.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ResearchContractError("Ollama adapter requires an evidence packet")
    items = evidence.get("evidence_items")
    if not isinstance(items, list):
        raise ResearchContractError("Ollama adapter requires evidence_items")

    source_ids: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ResearchContractError("Ollama evidence items must be objects")
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ResearchContractError("Ollama evidence items require non-empty source_id")
        if source_id in seen:
            raise ResearchContractError(f"Duplicate evidence source_id: {source_id!r}")
        seen.add(source_id)
        source_ids.append(source_id)
    return tuple(source_ids)


def _schema_for_request(request: Mapping[str, object]) -> dict[str, object]:
    """Constrain citations to the exact evidence IDs supplied for this question."""

    allowed_source_ids = _allowed_source_ids(request)
    schema = copy.deepcopy(STRUCTURED_FORECAST_SCHEMA)
    properties = schema["properties"]
    if not isinstance(properties, dict):
        raise ResearchContractError("Forecast schema properties are malformed")
    citation_schema = properties.get("cited_source_ids")
    if not isinstance(citation_schema, dict):
        raise ResearchContractError("Forecast citation schema is malformed")

    citation_schema["maxItems"] = len(allowed_source_ids)
    if allowed_source_ids:
        citation_schema["items"] = {
            "type": "string",
            "enum": list(allowed_source_ids),
        }
    else:
        # An empty enum is invalid JSON Schema. maxItems=0 makes [] the only valid array.
        citation_schema["items"] = {"type": "string"}
    return schema


def _deduplicate_cited_source_ids(parsed: dict[str, object]) -> dict[str, object]:
    """Remove repeated string citation IDs while preserving first-seen order.

    Ollama can occasionally violate JSON Schema ``uniqueItems`` even when every
    emitted ID is otherwise valid. Repeating the same citation carries no new
    information and must not turn an otherwise valid probability forecast into
    a failed forecast. Unknown IDs and malformed non-string values are left in
    place so downstream contract validation can still reject them.
    """

    citations = parsed.get("cited_source_ids")
    if not isinstance(citations, list):
        return parsed

    deduplicated: list[object] = []
    seen_strings: set[str] = set()
    for citation in citations:
        if isinstance(citation, str):
            if citation in seen_strings:
                continue
            seen_strings.add(citation)
        deduplicated.append(citation)

    if deduplicated == citations:
        return parsed
    normalized = dict(parsed)
    normalized["cited_source_ids"] = deduplicated
    return normalized


class OllamaStructuredModelAdapter:
    """Strict local Ollama adapter for one structured historical forecast response."""

    def __init__(
        self,
        *,
        model: str,
        metadata: ModelMetadata,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 180.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not model.strip():
            raise ResearchContractError("Ollama model tag cannot be empty")
        if not _IMMUTABLE_DIGEST.fullmatch(metadata.immutable_version):
            raise ResearchContractError(
                "Ollama historical scoring requires immutable_version=sha256:<64 hex digest>"
            )
        if metadata.execution_mode != "local":
            raise ResearchContractError("Ollama adapter requires execution_mode=local")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.model = model.strip()
        self.metadata = metadata
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate(self, request: Mapping[str, object]) -> Mapping[str, object]:
        payload: dict[str, object] = {
            "format": _schema_for_request(request),
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": canonical_json_bytes(dict(request)).decode("utf-8"),
                },
            ],
            "model": self.model,
            "options": {
                "seed": 0,
                "temperature": 0,
            },
            "stream": False,
        }
        try:
            response = self._client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ResearchContractError(f"Ollama request failed: {exc}") from exc

        if not isinstance(body, dict):
            raise ResearchContractError("Ollama response must be a JSON object")
        message = body.get("message")
        if not isinstance(message, dict):
            raise ResearchContractError("Ollama response is missing message object")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ResearchContractError("Ollama response is missing structured content")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ResearchContractError("Ollama structured content is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ResearchContractError("Ollama structured content must be a JSON object")
        return _deduplicate_cited_source_ids(parsed)
