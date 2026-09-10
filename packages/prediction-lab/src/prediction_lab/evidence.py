from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from prediction_lab.research_types import EvidenceItem, EvidencePacket, ResearchContractError


class EvidenceProvider(Protocol):
    """Offline-capable boundary for historically timestamped evidence."""

    def build_packet(
        self,
        *,
        question_id: str,
        forecasted_at: object,
        research_cutoff_at: object,
    ) -> EvidencePacket:
        """Return evidence known to be available by the requested cutoff."""


class FixtureEvidenceProvider:
    """Construct packets from an in-memory mapping used by tests and local fixtures."""

    def __init__(self, items_by_question: Mapping[str, Sequence[EvidenceItem]]) -> None:
        self._items_by_question = {
            str(question_id): tuple(items) for question_id, items in items_by_question.items()
        }

    def build_packet(
        self,
        *,
        question_id: str,
        forecasted_at: object,
        research_cutoff_at: object,
    ) -> EvidencePacket:
        if question_id not in self._items_by_question:
            raise ResearchContractError(
                f"Evidence fixture has no explicit entry for question {question_id}"
            )
        return EvidencePacket.create(
            question_id=question_id,
            forecasted_at=forecasted_at,
            research_cutoff_at=research_cutoff_at,
            evidence_items=self._items_by_question[question_id],
        )


class FileEvidenceProvider(FixtureEvidenceProvider):
    """Load immutable historical evidence from a local JSON fixture file."""

    def __init__(self, path: str | Path) -> None:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchContractError(f"Cannot load evidence fixture {source}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ResearchContractError("Evidence fixture must use schema_version 1")
        questions = payload.get("questions")
        if not isinstance(questions, dict):
            raise ResearchContractError("Evidence fixture questions must be an object")

        parsed: dict[str, tuple[EvidenceItem, ...]] = {}
        for question_id, raw_items in questions.items():
            if not isinstance(question_id, str) or not isinstance(raw_items, list):
                raise ResearchContractError("Evidence fixture entries must map IDs to item lists")
            if not all(isinstance(item, dict) for item in raw_items):
                raise ResearchContractError("Evidence fixture items must be objects")
            parsed[question_id] = tuple(EvidenceItem.from_dict(item) for item in raw_items)
        super().__init__(parsed)
