from __future__ import annotations

import copy

import pytest

from prediction_lab.research_types import ResearchContractError
from prediction_lab.residual_development_cli import (
    EXPECTED_EVIDENCE,
    PREREGISTRATION_COMMIT,
    _assert_preregistered_evidence_spec,
)


def test_preregistered_residual_evidence_lineage_is_exact() -> None:
    _assert_preregistered_evidence_spec(copy.deepcopy(EXPECTED_EVIDENCE))
    changed = copy.deepcopy(EXPECTED_EVIDENCE)
    changed["filtered_fixture_sha256"] = "0" * 64
    with pytest.raises(ResearchContractError, match="exact frozen relevance-v2"):
        _assert_preregistered_evidence_spec(changed)


def test_residual_preregistration_commit_is_frozen() -> None:
    assert PREREGISTRATION_COMMIT == "271a0866d1c2ebd4ffa70275f7d187e776fcdc75"
