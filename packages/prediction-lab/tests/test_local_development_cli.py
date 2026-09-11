from __future__ import annotations

from pathlib import Path

import pytest

from prediction_lab.local_development_cli import (
    _assert_loopback_ollama,
    _assert_work_root_outside_repository,
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
