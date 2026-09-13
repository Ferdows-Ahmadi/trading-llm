from __future__ import annotations

from typing import Any

from prediction_lab import prospective_evidence_v01 as evidence_contract
from prediction_lab import prospective_forecast_v01 as forecast
from prediction_lab.research_types import (
    EvidenceAvailability,
    EvidenceItem,
    EvidencePacket,
    ResearchContractError,
)
from prediction_lab.residual_adapter import residual_probability


def custody_row(*, probability: float = 0.55) -> dict[str, object]:
    return {
        "market_id": "123",
        "event_id": "event-1",
        "within_event_rank": 1,
        "question_text": "Will Example Corp launch Product X by November?",
        "description": "Resolves Yes if Product X is publicly launched before the deadline.",
        "scheduled_end_at": "2026-11-01T00:00:00Z",
        "source_cutoff_at": evidence_contract.SOURCE_CUTOFF,
        "market_price_timestamp": "2026-09-13T19:17:20Z",
        "market_probability": probability,
    }


def packet(*, with_evidence: bool) -> EvidencePacket:
    items = []
    if with_evidence:
        items = [
            EvidenceItem.create(
                source_id="source-1",
                source_type="gdelt-discovered-common-crawl-warc",
                uri_or_reference="commoncrawl://test",
                title="Example evidence",
                available_at="2026-09-12T00:00:00Z",
                retrieved_at="2026-09-14T00:00:00Z",
                text="Example Corp publicly discussed Product X launch plans.",
            )
        ]
    status = "verified_complete" if with_evidence else "verified_empty"
    availability = EvidenceAvailability(status, "test state")
    return EvidencePacket.create(
        question_id="polymarket-market:123",
        forecasted_at="2026-09-13T19:17:20Z",
        research_cutoff_at=evidence_contract.SOURCE_CUTOFF,
        evidence_items=items,
        availability=availability,
    )


class StubAdapter:
    def __init__(
        self,
        *,
        fail: bool = False,
        action: str = "increase",
        strength: str = "weak",
    ) -> None:
        self.fail = fail
        self.action = action
        self.strength = strength
        self.calls: list[dict[str, object]] = []
        self._records: dict[str, dict[str, object]] = {}

    def generate(self, request: dict[str, object]) -> dict[str, object]:
        self.calls.append(request)
        question = request["question"]
        assert isinstance(question, dict)
        question_id = str(question["question_id"])
        if self.fail:
            raise ResearchContractError("synthetic single-attempt failure")
        prior = float(request["market_probability"])
        magnitude = {"weak": 0.25, "moderate": 0.50, "strong": 0.75}[self.strength]
        if self.action == "abstain":
            delta = 0.0
            strength = "none"
        else:
            delta = magnitude if self.action == "increase" else -magnitude
            strength = self.strength
        final = residual_probability(prior, delta)
        self._records[question_id] = {
            "action": self.action,
            "cited_source_ids": ["source-1"] if self.action != "abstain" else [],
            "evidence_strength": strength,
            "final_probability": final,
            "hard_noop": False,
            "logit_delta": delta,
            "mapping_version": "logit-residual-v1",
            "market_probability": prior,
            "raw_model_output": {},
        }
        return {
            "base_rate_probability": prior,
            "updated_probability": final,
            "final_probability": final,
            "confidence_or_uncertainty": "synthetic",
            "critique": "synthetic",
            "cited_source_ids": ["source-1"] if self.action != "abstain" else [],
        }

    def decision_records(self) -> dict[str, dict[str, object]]:
        return {key: dict(value) for key, value in self._records.items()}


def run_row(
    *,
    with_evidence: bool,
    adapter: StubAdapter,
) -> dict[str, object]:
    return forecast.forecast_row(
        custody_row(),
        packet=packet(with_evidence=with_evidence),
        adapter=adapter,  # type: ignore[arg-type]
    )


def test_verified_empty_is_exact_noop_without_model_call() -> None:
    adapter = StubAdapter()
    result = run_row(with_evidence=False, adapter=adapter)

    assert result["status"] == "verified_empty_noop"
    assert result["action"] == "hard_noop"
    assert result["logit_delta"] == 0.0
    assert result["market_probability"] == 0.55
    assert result["final_probability"] == 0.55
    assert result["model_called"] is False
    assert adapter.calls == []


def test_evidence_row_uses_exact_residual_mapping_once() -> None:
    adapter = StubAdapter(action="increase", strength="moderate")
    result = run_row(with_evidence=True, adapter=adapter)

    assert len(adapter.calls) == 1
    assert result["status"] == "model_evaluated"
    assert result["action"] == "increase"
    assert result["evidence_strength"] == "moderate"
    assert result["logit_delta"] == 0.5
    assert result["final_probability"] == residual_probability(0.55, 0.5)
    request = adapter.calls[0]
    assert request["prompt_version"] == "market-residual-v2"
    assert request["mode"] == "market-aware"
    assert request["market_probability"] == 0.55
    question = request["question"]
    assert isinstance(question, dict)
    assert question["text"] == evidence_contract._canonical_problem_text(custody_row())


def test_model_failure_preserves_prior_and_denominator_without_retry() -> None:
    adapter = StubAdapter(fail=True)
    result = run_row(with_evidence=True, adapter=adapter)

    assert len(adapter.calls) == 1
    assert result["status"] == "model_failure_noop"
    assert result["action"] == "model_failure_noop"
    assert result["logit_delta"] == 0.0
    assert result["market_probability"] == 0.55
    assert result["final_probability"] == 0.55
    assert result["model_called"] is True
    assert result["failure_class"] == "ResearchContractError"


def test_nonterminal_evidence_state_is_forbidden() -> None:
    unavailable = EvidencePacket.create(
        question_id="polymarket-market:123",
        forecasted_at="2026-09-13T19:17:20Z",
        research_cutoff_at=evidence_contract.SOURCE_CUTOFF,
        evidence_items=[],
        availability=EvidenceAvailability("retrieval_failure", "synthetic failure"),
    )
    adapter = StubAdapter()

    try:
        forecast.forecast_row(
            custody_row(),
            packet=unavailable,
            adapter=adapter,  # type: ignore[arg-type]
        )
    except ResearchContractError as exc:
        assert "Forecasting forbidden" in str(exc)
    else:
        raise AssertionError("retrieval_failure must not be forecasted")
    assert adapter.calls == []


def test_forecast_record_contains_no_outcome_or_score_fields() -> None:
    result = run_row(with_evidence=True, adapter=StubAdapter())
    forbidden = {
        "outcome",
        "resolved_at",
        "resolution",
        "brier",
        "log_loss",
        "score",
        "label",
    }
    assert forbidden.isdisjoint(result)


def test_frozen_model_identity() -> None:
    metadata = forecast._model_metadata()
    assert forecast.MODEL_TAG == "llama3.1:8b"
    assert forecast.MODEL_DIGEST == (
        "sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e"
    )
    assert metadata.immutable_version == forecast.MODEL_DIGEST
    assert metadata.execution_mode == "local"
    assert metadata.contamination_assessment == "historical-safe"
    assert metadata.knowledge_cutoff.isoformat() == "2023-12-31T23:59:59+00:00"
