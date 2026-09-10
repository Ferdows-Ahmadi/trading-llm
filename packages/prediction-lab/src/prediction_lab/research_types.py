from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal


class ResearchContractError(ValueError):
    """Raised when a research artifact violates a reproducibility contract."""


ForecastMode = Literal["blind", "market-aware"]


def canonical_json_bytes(value: object) -> bytes:
    """Encode JSON deterministically for hashing and immutable artifact files."""

    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ResearchContractError("Value is not canonical JSON") from exc
    return text.encode("utf-8")


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_utc(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ResearchContractError(f"{field} must be a valid timestamp") from exc
    else:
        raise ResearchContractError(f"{field} must be a known timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchContractError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _non_empty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchContractError(f"{field} cannot be empty")
    return value.strip()


def _probability(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchContractError(f"{field} must be a finite probability in [0, 1]")
    probability = float(value)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ResearchContractError(f"{field} must be a finite probability in [0, 1]")
    return probability


@dataclass(frozen=True)
class EvidenceItem:
    source_id: str
    source_type: str
    uri_or_reference: str
    title: str
    available_at: datetime
    retrieved_at: datetime
    content_hash: str
    text: str

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        source_type: str,
        uri_or_reference: str,
        title: str,
        available_at: object,
        retrieved_at: object,
        text: str,
        expected_content_hash: str | None = None,
    ) -> EvidenceItem:
        item_text = _non_empty(text, field="text")
        actual_hash = _text_hash(item_text)
        if expected_content_hash is not None and expected_content_hash != actual_hash:
            raise ResearchContractError(
                "Evidence content hash mismatch: "
                f"expected {expected_content_hash}, got {actual_hash}"
            )
        availability_time = parse_utc(available_at, field="available_at")
        retrieval_time = parse_utc(retrieved_at, field="retrieved_at")
        if retrieval_time < availability_time:
            raise ResearchContractError("retrieved_at cannot be earlier than available_at")
        return cls(
            source_id=_non_empty(source_id, field="source_id"),
            source_type=_non_empty(source_type, field="source_type"),
            uri_or_reference=_non_empty(uri_or_reference, field="uri_or_reference"),
            title=_non_empty(title, field="title"),
            available_at=availability_time,
            retrieved_at=retrieval_time,
            content_hash=actual_hash,
            text=item_text,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> EvidenceItem:
        return cls.create(
            source_id=value.get("source_id"),  # type: ignore[arg-type]
            source_type=value.get("source_type"),  # type: ignore[arg-type]
            uri_or_reference=value.get("uri_or_reference"),  # type: ignore[arg-type]
            title=value.get("title"),  # type: ignore[arg-type]
            available_at=value.get("available_at"),
            retrieved_at=value.get("retrieved_at"),
            text=value.get("text"),  # type: ignore[arg-type]
            expected_content_hash=(
                str(value["content_hash"]) if value.get("content_hash") is not None else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "available_at": format_utc(self.available_at),
            "content_hash": self.content_hash,
            "retrieved_at": format_utc(self.retrieved_at),
            "source_id": self.source_id,
            "source_type": self.source_type,
            "text": self.text,
            "title": self.title,
            "uri_or_reference": self.uri_or_reference,
        }


@dataclass(frozen=True)
class EvidencePacket:
    question_id: str
    forecasted_at: datetime
    research_cutoff_at: datetime
    evidence_items: tuple[EvidenceItem, ...]
    packet_hash: str

    @classmethod
    def create(
        cls,
        *,
        question_id: str,
        forecasted_at: object,
        research_cutoff_at: object,
        evidence_items: Sequence[EvidenceItem],
    ) -> EvidencePacket:
        question = _non_empty(question_id, field="question_id")
        forecast_time = parse_utc(forecasted_at, field="forecasted_at")
        cutoff = parse_utc(research_cutoff_at, field="research_cutoff_at")
        if cutoff > forecast_time:
            raise ResearchContractError("research_cutoff_at cannot be after forecasted_at")
        items = tuple(evidence_items)
        source_ids = [item.source_id for item in items]
        if len(source_ids) != len(set(source_ids)):
            raise ResearchContractError("Evidence source_id values must be unique within a packet")
        for item in items:
            if item.available_at > cutoff:
                raise ResearchContractError(
                    f"Evidence {item.source_id} is newer than research cutoff"
                )
        payload = {
            "evidence_items": [item.to_dict() for item in items],
            "forecasted_at": format_utc(forecast_time),
            "question_id": question,
            "research_cutoff_at": format_utc(cutoff),
        }
        return cls(
            question_id=question,
            forecasted_at=forecast_time,
            research_cutoff_at=cutoff,
            evidence_items=items,
            packet_hash=content_hash(payload),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> EvidencePacket:
        raw_items = value.get("evidence_items")
        if not isinstance(raw_items, list) or not all(isinstance(item, dict) for item in raw_items):
            raise ResearchContractError("evidence_items must be a list of objects")
        packet = cls.create(
            question_id=value.get("question_id"),  # type: ignore[arg-type]
            forecasted_at=value.get("forecasted_at"),
            research_cutoff_at=value.get("research_cutoff_at"),
            evidence_items=[EvidenceItem.from_dict(item) for item in raw_items],
        )
        expected = value.get("packet_hash")
        if expected is not None and expected != packet.packet_hash:
            raise ResearchContractError("Evidence packet hash mismatch")
        return packet

    def assert_safe_for_cutoff(self, cutoff: object) -> None:
        current_cutoff = parse_utc(cutoff, field="forecast cutoff")
        if self.research_cutoff_at > current_cutoff:
            raise ResearchContractError("Cached evidence packet is newer than forecast cutoff")
        for item in self.evidence_items:
            if item.available_at > current_cutoff:
                raise ResearchContractError(
                    f"Cached evidence {item.source_id} is newer than forecast cutoff"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_items": [item.to_dict() for item in self.evidence_items],
            "forecasted_at": format_utc(self.forecasted_at),
            "packet_hash": self.packet_hash,
            "question_id": self.question_id,
            "research_cutoff_at": format_utc(self.research_cutoff_at),
        }


@dataclass(frozen=True)
class ModelMetadata:
    provider: str
    model_id: str
    immutable_version: str
    release_date: datetime
    knowledge_cutoff: datetime
    execution_mode: Literal["local", "api"]
    contamination_assessment: Literal["historical-safe", "unknown", "contaminated"]
    contamination_notes: str

    @classmethod
    def create(
        cls,
        *,
        provider: str,
        model_id: str,
        immutable_version: str,
        release_date: object,
        knowledge_cutoff: object,
        execution_mode: str,
        contamination_assessment: str,
        contamination_notes: str,
    ) -> ModelMetadata:
        if execution_mode not in {"local", "api"}:
            raise ResearchContractError("execution_mode must be local or api")
        if contamination_assessment not in {"historical-safe", "unknown", "contaminated"}:
            raise ResearchContractError("Invalid contamination_assessment")
        return cls(
            provider=_non_empty(provider, field="provider"),
            model_id=_non_empty(model_id, field="model_id"),
            immutable_version=_non_empty(immutable_version, field="immutable_version"),
            release_date=parse_utc(release_date, field="release_date"),
            knowledge_cutoff=parse_utc(knowledge_cutoff, field="knowledge_cutoff"),
            execution_mode=execution_mode,  # type: ignore[arg-type]
            contamination_assessment=contamination_assessment,  # type: ignore[arg-type]
            contamination_notes=_non_empty(contamination_notes, field="contamination_notes"),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ModelMetadata:
        return cls.create(
            provider=value.get("provider"),  # type: ignore[arg-type]
            model_id=value.get("model_id"),  # type: ignore[arg-type]
            immutable_version=value.get("immutable_version"),  # type: ignore[arg-type]
            release_date=value.get("release_date"),
            knowledge_cutoff=value.get("knowledge_cutoff"),
            execution_mode=str(value.get("execution_mode", "")),
            contamination_assessment=str(value.get("contamination_assessment", "")),
            contamination_notes=value.get("contamination_notes"),  # type: ignore[arg-type]
        )

    def assert_safe_for_historical_scoring(self, forecasted_at: object) -> None:
        forecast_time = parse_utc(forecasted_at, field="forecasted_at")
        if self.contamination_assessment != "historical-safe":
            raise ResearchContractError(
                "Historical scoring requires an explicit historical-safe contamination assessment"
            )
        if self.release_date > forecast_time:
            raise ResearchContractError("Model release date is after the historical forecast")
        if self.knowledge_cutoff > forecast_time:
            raise ResearchContractError("Model knowledge cutoff is after the historical forecast")

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["release_date"] = format_utc(self.release_date)
        result["knowledge_cutoff"] = format_utc(self.knowledge_cutoff)
        return result


@dataclass(frozen=True)
class StructuredForecastOutput:
    base_rate_probability: float
    updated_probability: float
    final_probability: float
    confidence_or_uncertainty: str
    critique: str
    cited_source_ids: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> StructuredForecastOutput:
        required = {
            "base_rate_probability",
            "updated_probability",
            "final_probability",
            "confidence_or_uncertainty",
            "critique",
            "cited_source_ids",
        }
        if set(value) != required:
            missing = sorted(required - set(value))
            unexpected = sorted(set(value) - required)
            raise ResearchContractError(
                f"Malformed structured model output; missing={missing}, unexpected={unexpected}"
            )
        citations = value["cited_source_ids"]
        if not isinstance(citations, list) or not all(isinstance(item, str) for item in citations):
            raise ResearchContractError("cited_source_ids must be a list of strings")
        normalized_citations = tuple(
            _non_empty(item, field="cited_source_id") for item in citations
        )
        if len(normalized_citations) != len(set(normalized_citations)):
            raise ResearchContractError("cited_source_ids cannot contain duplicates")
        return cls(
            base_rate_probability=_probability(
                value["base_rate_probability"], field="base_rate_probability"
            ),
            updated_probability=_probability(
                value["updated_probability"], field="updated_probability"
            ),
            final_probability=_probability(value["final_probability"], field="final_probability"),
            confidence_or_uncertainty=_non_empty(
                value["confidence_or_uncertainty"], field="confidence_or_uncertainty"
            ),
            critique=_non_empty(value["critique"], field="critique"),
            cited_source_ids=normalized_citations,
        )


@dataclass(frozen=True)
class ForecastArtifact:
    experiment_id: str
    benchmark_hash: str
    code_commit: str
    experiment_config_hash: str
    question_id: str
    forecasted_at: datetime
    model_metadata: ModelMetadata
    blind_or_market_aware: ForecastMode
    base_rate_probability: float
    updated_probability: float
    final_probability: float
    confidence_or_uncertainty: str
    critique: str
    cited_source_ids: tuple[str, ...]
    prompt_version: str
    evidence_packet_hash: str
    raw_structured_model_output: Mapping[str, object]
    cache_key: str
    artifact_hash: str

    @classmethod
    def create(
        cls,
        *,
        experiment_id: str,
        benchmark_hash: str,
        code_commit: str,
        experiment_config_hash: str,
        question_id: str,
        forecasted_at: object,
        model_metadata: ModelMetadata,
        blind_or_market_aware: ForecastMode,
        output: StructuredForecastOutput,
        prompt_version: str,
        evidence_packet_hash: str,
        raw_structured_model_output: Mapping[str, object],
        cache_key: str,
    ) -> ForecastArtifact:
        if blind_or_market_aware not in {"blind", "market-aware"}:
            raise ResearchContractError("Invalid forecast mode")
        raw = dict(raw_structured_model_output)
        frozen_raw = MappingProxyType(
            {
                **raw,
                "cited_source_ids": tuple(output.cited_source_ids),
            }
        )
        payload: dict[str, object] = {
            "base_rate_probability": output.base_rate_probability,
            "benchmark_hash": _non_empty(benchmark_hash, field="benchmark_hash"),
            "blind_or_market_aware": blind_or_market_aware,
            "cache_key": _non_empty(cache_key, field="cache_key"),
            "cited_source_ids": list(output.cited_source_ids),
            "code_commit": _non_empty(code_commit, field="code_commit"),
            "confidence_or_uncertainty": output.confidence_or_uncertainty,
            "critique": output.critique,
            "evidence_packet_hash": _non_empty(evidence_packet_hash, field="evidence_packet_hash"),
            "experiment_config_hash": _non_empty(
                experiment_config_hash, field="experiment_config_hash"
            ),
            "experiment_id": _non_empty(experiment_id, field="experiment_id"),
            "final_probability": output.final_probability,
            "forecasted_at": format_utc(parse_utc(forecasted_at, field="forecasted_at")),
            "model_metadata": model_metadata.to_dict(),
            "prompt_version": _non_empty(prompt_version, field="prompt_version"),
            "question_id": _non_empty(question_id, field="question_id"),
            "raw_structured_model_output": raw,
            "updated_probability": output.updated_probability,
        }
        digest = content_hash(payload)
        return cls(
            experiment_id=str(payload["experiment_id"]),
            benchmark_hash=str(payload["benchmark_hash"]),
            code_commit=str(payload["code_commit"]),
            experiment_config_hash=str(payload["experiment_config_hash"]),
            question_id=str(payload["question_id"]),
            forecasted_at=parse_utc(payload["forecasted_at"], field="forecasted_at"),
            model_metadata=model_metadata,
            blind_or_market_aware=blind_or_market_aware,
            base_rate_probability=output.base_rate_probability,
            updated_probability=output.updated_probability,
            final_probability=output.final_probability,
            confidence_or_uncertainty=output.confidence_or_uncertainty,
            critique=output.critique,
            cited_source_ids=output.cited_source_ids,
            prompt_version=str(payload["prompt_version"]),
            evidence_packet_hash=str(payload["evidence_packet_hash"]),
            raw_structured_model_output=frozen_raw,
            cache_key=str(payload["cache_key"]),
            artifact_hash=digest,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ForecastArtifact:
        raw_output = value.get("raw_structured_model_output")
        metadata = value.get("model_metadata")
        if not isinstance(raw_output, dict) or not isinstance(metadata, dict):
            raise ResearchContractError("Malformed forecast artifact")
        output = StructuredForecastOutput.from_mapping(raw_output)
        artifact = cls.create(
            experiment_id=value.get("experiment_id"),  # type: ignore[arg-type]
            benchmark_hash=value.get("benchmark_hash"),  # type: ignore[arg-type]
            code_commit=value.get("code_commit"),  # type: ignore[arg-type]
            experiment_config_hash=value.get("experiment_config_hash"),  # type: ignore[arg-type]
            question_id=value.get("question_id"),  # type: ignore[arg-type]
            forecasted_at=value.get("forecasted_at"),
            model_metadata=ModelMetadata.from_dict(metadata),
            blind_or_market_aware=value.get("blind_or_market_aware"),  # type: ignore[arg-type]
            output=output,
            prompt_version=value.get("prompt_version"),  # type: ignore[arg-type]
            evidence_packet_hash=value.get("evidence_packet_hash"),  # type: ignore[arg-type]
            raw_structured_model_output=raw_output,
            cache_key=value.get("cache_key"),  # type: ignore[arg-type]
        )
        if value.get("artifact_hash") != artifact.artifact_hash:
            raise ResearchContractError("Forecast artifact hash mismatch")
        if dict(value) != artifact.to_dict():
            raise ResearchContractError("Forecast artifact fields are inconsistent")
        return artifact

    def to_dict(self) -> dict[str, Any]:
        raw_output = dict(self.raw_structured_model_output)
        raw_output["cited_source_ids"] = list(self.cited_source_ids)
        return {
            "artifact_hash": self.artifact_hash,
            "base_rate_probability": self.base_rate_probability,
            "benchmark_hash": self.benchmark_hash,
            "blind_or_market_aware": self.blind_or_market_aware,
            "cache_key": self.cache_key,
            "cited_source_ids": list(self.cited_source_ids),
            "code_commit": self.code_commit,
            "confidence_or_uncertainty": self.confidence_or_uncertainty,
            "critique": self.critique,
            "evidence_packet_hash": self.evidence_packet_hash,
            "experiment_config_hash": self.experiment_config_hash,
            "experiment_id": self.experiment_id,
            "final_probability": self.final_probability,
            "forecasted_at": format_utc(self.forecasted_at),
            "model_metadata": self.model_metadata.to_dict(),
            "prompt_version": self.prompt_version,
            "question_id": self.question_id,
            "raw_structured_model_output": raw_output,
            "updated_probability": self.updated_probability,
        }
