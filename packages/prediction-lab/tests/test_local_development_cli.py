from __future__ import annotations

import json
from pathlib import Path

import pytest

from prediction_lab.local_development_cli import (
    EVIDENCE_ARTIFACT,
    EVIDENCE_RUN_ID,
    FILTERED_FIXTURE_SHA256,
    _assert_loopback_ollama,
    _assert_work_root_outside_repository,
    _load_evidence_spec,
    _select_model_digest,
)
from prediction_lab.research_types import ResearchContractError


def test_select_model_digest_normalizes_raw_digest() -> None:
    raw = "a" * 64
    payload = {
        "models": [
            {
                "name": "llama3.1:8b",
                "model": "llama3.1:8b",
                "digest": raw,
            }
        ]
    }

    assert _select_model_digest(payload, "llama3.1:8b") == f"sha256:{raw}"


def test_select_model_digest_returns_none_for_missing_model() -> None:
    payload = {
        "models": [
            {
                "name": "another:latest",
                "digest": f"sha256:{'b' * 64}",
            }
        ]
    }

    assert _select_model_digest(payload, "llama3.1:8b") is None


def test_select_model_digest_rejects_invalid_digest() -> None:
    payload = {
        "models": [
            {
                "name": "llama3.1:8b",
                "digest": "not-a-digest",
            }
        ]
    }

    with pytest.raises(ResearchContractError, match="invalid model digest"):
        _select_model_digest(payload, "llama3.1:8b")


def test_loopback_ollama_endpoint_is_required() -> None:
    _assert_loopback_ollama("http://127.0.0.1:11434")
    _assert_loopback_ollama("http://localhost:11434")

    with pytest.raises(ResearchContractError, match="loopback Ollama endpoint"):
        _assert_loopback_ollama("https://example.com")


def test_work_root_must_live_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(ResearchContractError, match="outside the Git checkout"):
        _assert_work_root_outside_repository(repository, repository / "runs")

    sibling = tmp_path / "research-runs"
    assert _assert_work_root_outside_repository(repository, sibling) == sibling.resolve()


def test_default_evidence_spec_preserves_original_v1_lineage(tmp_path: Path) -> None:
    spec = _load_evidence_spec(tmp_path, None)

    assert spec["workflow_run"] == EVIDENCE_RUN_ID
    assert spec["artifact"] == EVIDENCE_ARTIFACT
    assert spec["filtered_fixture_sha256"] == FILTERED_FIXTURE_SHA256
    assert spec["expected_summary"] == {
        "method_version": "lexical-relevance-v1",
        "pilot_questions": 20,
        "raw_items": 94,
        "kept_items": 16,
        "questions_with_kept": 8,
        "questions_without_kept": 12,
    }


def test_checked_in_style_evidence_spec_can_select_frozen_v2_lineage(
    tmp_path: Path,
) -> None:
    spec_path = tmp_path / "evidence-v2.json"
    payload = {
        "schema_version": 1,
        "workflow_run": 34689232387,
        "artifact": "evidence-relevance-filter-v0.2",
        "artifact_digest": f"sha256:{'a' * 64}",
        "filtered_fixture_sha256": "b" * 64,
        "artifact_code_commit": "c" * 40,
        "preregistration_commit": "d" * 40,
        "expected_summary": {
            "method_version": "lexical-relevance-v2",
            "pilot_questions": 20,
            "raw_items": 94,
            "kept_items": 7,
            "questions_with_kept": 4,
            "questions_without_kept": 16,
        },
    }
    spec_path.write_text(json.dumps(payload), encoding="utf-8")

    assert _load_evidence_spec(tmp_path, Path("evidence-v2.json")) == payload


def test_evidence_spec_rejects_malformed_lineage(tmp_path: Path) -> None:
    spec_path = tmp_path / "bad.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workflow_run": 0,
                "artifact": "evidence",
                "artifact_digest": f"sha256:{'a' * 64}",
                "filtered_fixture_sha256": "b" * 64,
                "expected_summary": {"method_version": "lexical-relevance-v2"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ResearchContractError, match="workflow_run"):
        _load_evidence_spec(tmp_path, spec_path)
