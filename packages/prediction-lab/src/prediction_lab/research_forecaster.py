from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from prediction_lab.research_cache import FilesystemForecastCache, forecast_cache_key
from prediction_lab.research_types import (
    EvidencePacket,
    ForecastArtifact,
    ForecastMode,
    ModelMetadata,
    ResearchContractError,
    StructuredForecastOutput,
    canonical_json_bytes,
    content_hash,
    format_utc,
)

PROMPT_STAGES = (
    "base-rate estimate",
    "evidence synthesis/update",
    "adversarial critique",
    "final probability",
)


class StructuredModelAdapter(Protocol):
    """Provider-neutral boundary for one strict structured forecast response."""

    metadata: ModelMetadata

    def generate(self, request: Mapping[str, object]) -> Mapping[str, object]:
        """Return exactly the documented structured forecast fields."""


@dataclass
class DeterministicFakeModelAdapter:
    """Network-free adapter for reproducible orchestration and CI tests."""

    fail_question_ids: frozenset[str] = frozenset()
    metadata: ModelMetadata = field(init=False)

    def __post_init__(self) -> None:
        self.metadata = ModelMetadata.create(
            provider="offline-test",
            model_id="deterministic-fake",
            immutable_version="sha256-v1",
            release_date="2020-01-01T00:00:00Z",
            knowledge_cutoff="2020-01-01T00:00:00Z",
            execution_mode="local",
            contamination_assessment="historical-safe",
            contamination_notes="Algorithmic test double with no learned event knowledge.",
        )

    def generate(self, request: Mapping[str, object]) -> Mapping[str, object]:
        question = request.get("question")
        if not isinstance(question, dict) or not isinstance(question.get("question_id"), str):
            raise ResearchContractError("Fake adapter received a malformed question")
        question_id = question["question_id"]
        if question_id in self.fail_question_ids:
            raise ResearchContractError(f"Configured fake-model failure for {question_id}")

        digest = hashlib.sha256(canonical_json_bytes(request)).digest()
        unit = int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)
        base_rate = round(0.2 + 0.6 * unit, 6)
        evidence = request.get("evidence")
        if not isinstance(evidence, dict):
            raise ResearchContractError("Fake adapter requires an evidence packet")
        items = evidence.get("evidence_items")
        if not isinstance(items, list):
            raise ResearchContractError("Fake adapter requires evidence_items")
        evidence_shift = min(len(items), 5) * 0.01
        updated = min(1.0, max(0.0, base_rate + evidence_shift))
        market_probability = request.get("market_probability")
        if market_probability is not None:
            if isinstance(market_probability, bool) or not isinstance(
                market_probability, (int, float)
            ):
                raise ResearchContractError("market_probability must be numeric")
            updated = (updated + float(market_probability)) / 2.0
        final = round(min(1.0, max(0.0, updated - 0.01)), 6)
        citations = [
            item["source_id"]
            for item in items
            if isinstance(item, dict) and isinstance(item.get("source_id"), str)
        ]
        return {
            "base_rate_probability": base_rate,
            "cited_source_ids": citations,
            "confidence_or_uncertainty": "deterministic fixture; not a scientific forecast",
            "critique": "The offline fake model has no evidentiary forecasting skill.",
            "final_probability": final,
            "updated_probability": round(updated, 6),
        }


def _model_facing_evidence(evidence_packet: EvidencePacket) -> dict[str, object]:
    """Project persisted evidence into a historical-safe model input.

    Operational provenance such as retrieval time, archive URI, content hashes, and
    packet hashes is retained in persisted artifacts but never shown to the model.
    Those fields can reveal post-forecast context without contributing evidence that
    was actually available at historical time T.
    """

    return {
        "evidence_items": [
            {
                "available_at": format_utc(item.available_at),
                "source_id": item.source_id,
                "source_type": item.source_type,
                "text": item.text,
                "title": item.title,
            }
            for item in evidence_packet.evidence_items
        ],
        "forecasted_at": format_utc(evidence_packet.forecasted_at),
        "question_id": evidence_packet.question_id,
        "research_cutoff_at": format_utc(evidence_packet.research_cutoff_at),
    }


def build_model_request(
    *,
    question_id: str,
    question_text: str,
    evidence_packet: EvidencePacket,
    prompt_version: str,
    mode: ForecastMode,
    market_probability: float | None,
) -> dict[str, object]:
    """Build the adapter request without labels, resolutions, or future metadata."""

    if mode == "blind" and market_probability is not None:
        raise ResearchContractError("Blind requests cannot include market_probability")
    if mode == "market-aware" and market_probability is None:
        raise ResearchContractError("Market-aware requests require market_probability")
    if mode == "market-aware" and (
        isinstance(market_probability, bool)
        or not isinstance(market_probability, (int, float))
        or not math.isfinite(float(market_probability))
        or not 0.0 <= float(market_probability) <= 1.0
    ):
        raise ResearchContractError("market_probability must be finite and within [0, 1]")
    request: dict[str, object] = {
        "evidence": _model_facing_evidence(evidence_packet),
        "instructions": {
            "output_fields": [
                "base_rate_probability",
                "updated_probability",
                "critique",
                "final_probability",
                "confidence_or_uncertainty",
                "cited_source_ids",
            ],
            "stages": list(PROMPT_STAGES),
        },
        "mode": mode,
        "prompt_version": prompt_version,
        "question": {
            "forecasted_at": format_utc(evidence_packet.forecasted_at),
            "question_id": question_id,
            "research_cutoff_at": format_utc(evidence_packet.research_cutoff_at),
            "text": question_text,
        },
        "schema_version": 1,
    }
    if mode == "market-aware":
        request["market_probability"] = market_probability
    return request


def forecast_question(
    *,
    experiment_id: str,
    benchmark_hash: str,
    code_commit: str,
    experiment_config_hash: str,
    question_id: str,
    question_text: str,
    evidence_packet: EvidencePacket,
    prompt_version: str,
    mode: ForecastMode,
    market_probability: float | None,
    adapter: StructuredModelAdapter,
    cache: FilesystemForecastCache,
) -> tuple[ForecastArtifact, bool]:
    """Run or resume one historical forecast and return ``(artifact, cache_hit)``."""

    if evidence_packet.question_id != question_id:
        raise ResearchContractError("Evidence packet question_id mismatch")
    adapter.metadata.assert_safe_for_historical_scoring(evidence_packet.forecasted_at)
    request = build_model_request(
        question_id=question_id,
        question_text=question_text,
        evidence_packet=evidence_packet,
        prompt_version=prompt_version,
        mode=mode,
        market_probability=market_probability,
    )
    key = forecast_cache_key(
        code_commit=code_commit,
        model_request_hash=content_hash(request),
        evidence_packet_hash=evidence_packet.packet_hash,
        prompt_version=prompt_version,
        model_metadata=adapter.metadata.to_dict(),
        mode=mode,
        experiment_config_hash=experiment_config_hash,
    )
    cached = cache.load(
        key,
        evidence_packet=evidence_packet,
        forecast_cutoff_at=evidence_packet.research_cutoff_at,
    )
    if cached is not None:
        if (
            cached.experiment_id != experiment_id
            or cached.code_commit != code_commit
            or cached.experiment_config_hash != experiment_config_hash
            or cached.question_id != question_id
            or cached.prompt_version != prompt_version
            or cached.blind_or_market_aware != mode
            or cached.model_metadata != adapter.metadata
        ):
            raise ResearchContractError("Cached forecast metadata does not match current inputs")
        return cached, True

    raw = dict(adapter.generate(request))
    parsed = StructuredForecastOutput.from_mapping(raw)
    allowed_sources = {item.source_id for item in evidence_packet.evidence_items}
    unknown_sources = sorted(set(parsed.cited_source_ids) - allowed_sources)
    if unknown_sources:
        raise ResearchContractError(f"Model cited unknown evidence sources: {unknown_sources}")
    artifact = ForecastArtifact.create(
        experiment_id=experiment_id,
        benchmark_hash=benchmark_hash,
        code_commit=code_commit,
        experiment_config_hash=experiment_config_hash,
        question_id=question_id,
        forecasted_at=evidence_packet.forecasted_at,
        model_metadata=adapter.metadata,
        blind_or_market_aware=mode,
        output=parsed,
        prompt_version=prompt_version,
        evidence_packet_hash=evidence_packet.packet_hash,
        raw_structured_model_output=raw,
        cache_key=key,
    )
    cache.store(artifact)
    return artifact, False
