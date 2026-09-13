"""Inactive engineering successor. No CLI/workflow enables scientific use.

Requires separate preregistration before a real experiment. Mapping and system
prompt are inherited unchanged from residual-v1; only contradictory user
instructions are replaced.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from prediction_lab.research_types import ResearchContractError
from prediction_lab.residual_adapter import OllamaMarketResidualAdapter

PROMPT_VERSION = "market-residual-v2"
RESIDUAL_INSTRUCTIONS: dict[str, object] = {
    "output_fields": [
        "action",
        "evidence_strength",
        "confidence_or_uncertainty",
        "critique",
        "cited_source_ids",
    ],
    "stages": ["evidence synthesis/update", "adversarial critique", "residual decision"],
}


def residual_instructions() -> dict[str, object]:
    return copy.deepcopy(RESIDUAL_INSTRUCTIONS)


class OllamaMarketResidualV2Adapter(OllamaMarketResidualAdapter):
    """Explicit opt-in library path; legacy adapters and requests stay unchanged."""

    def generate(self, request: Mapping[str, object]) -> Mapping[str, object]:
        if request.get("prompt_version") != PROMPT_VERSION:
            raise ResearchContractError("Residual-v2 adapter requires market-residual-v2 request")
        if request.get("instructions") != RESIDUAL_INSTRUCTIONS:
            raise ResearchContractError("Residual-v2 request has contradictory output instructions")
        return super().generate(request)
