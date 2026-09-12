from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Mapping

import httpx

from prediction_lab.research_types import (
    ModelMetadata,
    ResearchContractError,
    canonical_json_bytes,
)

_IMMUTABLE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
RESIDUAL_MAPPING_VERSION = "logit-residual-v1"
MAX_ABS_LOGIT_DELTA = 0.75
STRENGTH_TO_ABS_DELTA = {
    "weak": 0.25,
    "moderate": 0.50,
    "strong": 0.75,
}

RESIDUAL_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": ["increase", "decrease", "abstain"],
        },
        "evidence_strength": {
            "type": "string",
            "enum": ["none", "weak", "moderate", "strong"],
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
        "action",
        "evidence_strength",
        "confidence_or_uncertainty",
        "critique",
        "cited_source_ids",
    ],
}

_SYSTEM_PROMPT = """You are a historical evidence analyst assisting a prediction-market forecaster.
The supplied market probability is the prior. Do not emit any probability or numeric adjustment.
Use only the supplied question, market prior, and historical evidence.
Decide whether the evidence justifies increasing the market probability, decreasing it, or abstaining.
Use evidence_strength=none only with abstain. Use weak/moderate/strong only with increase or decrease.
Prefer abstention when the evidence is not specifically decision-relevant or does not clearly move the prior.
Cite only source IDs present in the evidence payload.
Return exactly one JSON object matching the schema.
"""


def _market_probability(request: Mapping[str, object]) -> float:
    value = request.get("market_probability")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchContractError("Residual adapter requires numeric market_probability")
    probability = float(value)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ResearchContractError("market_probability must be finite and within [0, 1]")
    if request.get("mode") != "market-aware":
        raise ResearchContractError("Residual adapter accepts market-aware requests only")
    return probability


def _question_id(request: Mapping[str, object]) -> str:
    question = request.get("question")
    if not isinstance(question, Mapping):
        raise ResearchContractError("Residual adapter requires a question object")
    value = question.get("question_id")
    if not isinstance(value, str) or not value.strip():
        raise ResearchContractError("Residual adapter requires question_id")
    return value.strip()


def _allowed_source_ids(request: Mapping[str, object]) -> tuple[str, ...]:
    evidence = request.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ResearchContractError("Residual adapter requires an evidence packet")
    items = evidence.get("evidence_items")
    if not isinstance(items, list):
        raise ResearchContractError("Residual adapter requires evidence_items")

    source_ids: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ResearchContractError("Residual evidence items must be objects")
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise ResearchContractError("Residual evidence items require non-empty source_id")
        if source_id in seen:
            raise ResearchContractError(f"Duplicate evidence source_id: {source_id!r}")
        seen.add(source_id)
        source_ids.append(source_id)
    return tuple(source_ids)


def _schema_for_request(request: Mapping[str, object]) -> dict[str, object]:
    allowed_source_ids = _allowed_source_ids(request)
    if not allowed_source_ids:
        raise ResearchContractError("Zero-evidence residual requests must use the hard no-op path")
    schema = copy.deepcopy(RESIDUAL_DECISION_SCHEMA)
    properties = schema["properties"]
    if not isinstance(properties, dict):
        raise ResearchContractError("Residual schema properties are malformed")
    citations = properties.get("cited_source_ids")
    if not isinstance(citations, dict):
        raise ResearchContractError("Residual citation schema is malformed")
    citations["maxItems"] = len(allowed_source_ids)
    citations["items"] = {
        "type": "string",
        "enum": list(allowed_source_ids),
    }
    return schema


def _deduplicate_citations(parsed: dict[str, object]) -> dict[str, object]:
    citations = parsed.get("cited_source_ids")
    if not isinstance(citations, list):
        return parsed
    result: list[object] = []
    seen: set[str] = set()
    for citation in citations:
        if isinstance(citation, str):
            if citation in seen:
                continue
            seen.add(citation)
        result.append(citation)
    if result == citations:
        return parsed
    normalized = dict(parsed)
    normalized["cited_source_ids"] = result
    return normalized


def _validate_decision(
    value: Mapping[str, object],
    *,
    allowed_source_ids: tuple[str, ...],
) -> tuple[str, str, str, str, list[str]]:
    expected = {
        "action",
        "evidence_strength",
        "confidence_or_uncertainty",
        "critique",
        "cited_source_ids",
    }
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unexpected = sorted(set(value) - expected)
        raise ResearchContractError(
            f"Malformed residual output; missing={missing}, unexpected={unexpected}"
        )

    action = value["action"]
    strength = value["evidence_strength"]
    confidence = value["confidence_or_uncertainty"]
    critique = value["critique"]
    citations = value["cited_source_ids"]
    if action not in {"increase", "decrease", "abstain"}:
        raise ResearchContractError("Residual action is invalid")
    if strength not in {"none", "weak", "moderate", "strong"}:
        raise ResearchContractError("Residual evidence_strength is invalid")
    if action == "abstain" and strength != "none":
        raise ResearchContractError("Residual abstention requires evidence_strength=none")
    if action != "abstain" and strength == "none":
        raise ResearchContractError("Residual movement requires non-none evidence_strength")
    if not isinstance(confidence, str) or not confidence.strip():
        raise ResearchContractError("Residual confidence_or_uncertainty cannot be empty")
    if not isinstance(critique, str) or not critique.strip():
        raise ResearchContractError("Residual critique cannot be empty")
    if not isinstance(citations, list) or not all(isinstance(item, str) for item in citations):
        raise ResearchContractError("Residual cited_source_ids must be a list of strings")
    if len(citations) != len(set(citations)):
        raise ResearchContractError("Residual cited_source_ids cannot contain duplicates")
    unknown = sorted(set(citations) - set(allowed_source_ids))
    if unknown:
        raise ResearchContractError(f"Residual model cited unknown evidence sources: {unknown}")
    return action, strength, confidence.strip(), critique.strip(), citations


def residual_probability(market_probability: float, logit_delta: float) -> float:
    if not 0.0 <= market_probability <= 1.0:
        raise ResearchContractError("market_probability must be within [0, 1]")
    if not math.isfinite(logit_delta) or abs(logit_delta) > MAX_ABS_LOGIT_DELTA:
        raise ResearchContractError("logit_delta exceeds preregistered residual bound")
    if market_probability in {0.0, 1.0} or logit_delta == 0.0:
        return market_probability
    logit = math.log(market_probability / (1.0 - market_probability))
    updated_logit = logit + logit_delta
    return 1.0 / (1.0 + math.exp(-updated_logit))


class OllamaMarketResidualAdapter:
    """Preregistered bounded market-residual adapter for historical development scoring."""

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
                "Residual historical scoring requires immutable_version=sha256:<64 hex digest>"
            )
        if metadata.execution_mode != "local":
            raise ResearchContractError("Residual Ollama adapter requires execution_mode=local")
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
        self._decision_records: dict[str, dict[str, object]] = {}

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def decision_records(self) -> dict[str, dict[str, object]]:
        return {key: dict(value) for key, value in sorted(self._decision_records.items())}

    def _translated_output(
        self,
        *,
        question_id: str,
        market_probability: float,
        action: str,
        strength: str,
        logit_delta: float,
        confidence: str,
        critique: str,
        citations: list[str],
        hard_noop: bool,
        raw_model_output: Mapping[str, object] | None,
    ) -> Mapping[str, object]:
        final_probability = residual_probability(market_probability, logit_delta)
        record = {
            "action": action,
            "cited_source_ids": list(citations),
            "evidence_strength": strength,
            "final_probability": final_probability,
            "hard_noop": hard_noop,
            "logit_delta": logit_delta,
            "mapping_version": RESIDUAL_MAPPING_VERSION,
            "market_probability": market_probability,
            "raw_model_output": dict(raw_model_output) if raw_model_output is not None else None,
        }
        if question_id in self._decision_records:
            raise ResearchContractError(f"Duplicate residual decision for question {question_id!r}")
        self._decision_records[question_id] = record
        return {
            "base_rate_probability": market_probability,
            "updated_probability": final_probability,
            "final_probability": final_probability,
            "confidence_or_uncertainty": confidence,
            "critique": critique,
            "cited_source_ids": list(citations),
        }

    def generate(self, request: Mapping[str, object]) -> Mapping[str, object]:
        market_probability = _market_probability(request)
        question_id = _question_id(request)
        allowed_source_ids = _allowed_source_ids(request)

        if not allowed_source_ids:
            return self._translated_output(
                question_id=question_id,
                market_probability=market_probability,
                action="hard_noop",
                strength="none",
                logit_delta=0.0,
                confidence="deterministic no-op: no retained evidence",
                critique=(
                    "No relevance-v2 evidence was supplied; the market prior is preserved exactly."
                ),
                citations=[],
                hard_noop=True,
                raw_model_output=None,
            )

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
            raise ResearchContractError(f"Residual Ollama request failed: {exc}") from exc

        if not isinstance(body, dict):
            raise ResearchContractError("Residual Ollama response must be a JSON object")
        message = body.get("message")
        if not isinstance(message, dict):
            raise ResearchContractError("Residual Ollama response is missing message object")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ResearchContractError("Residual Ollama response is missing structured content")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ResearchContractError("Residual structured content is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ResearchContractError("Residual structured content must be a JSON object")
        parsed = _deduplicate_citations(parsed)
        action, strength, confidence, critique, citations = _validate_decision(
            parsed,
            allowed_source_ids=allowed_source_ids,
        )

        if action == "abstain":
            delta = 0.0
        else:
            magnitude = STRENGTH_TO_ABS_DELTA[strength]
            delta = magnitude if action == "increase" else -magnitude

        return self._translated_output(
            question_id=question_id,
            market_probability=market_probability,
            action=action,
            strength=strength,
            logit_delta=delta,
            confidence=confidence,
            critique=critique,
            citations=citations,
            hard_noop=False,
            raw_model_output=parsed,
        )
