from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from prediction_lab import prospective_model_freeze_v02 as freeze


def _client(models: list[dict[str, str]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": models}, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _digest(char: str) -> str:
    return "sha256:" + char * 64


def test_freezes_exact_three_model_manifest(tmp_path: Path) -> None:
    models = [
        {"name": "qwen3.5:9b", "digest": _digest("b")},
        {"name": "llama3.1:8b", "digest": _digest("a")},
        {"name": "deepseek-r1:8b", "digest": _digest("c")},
        {"name": "irrelevant:latest", "digest": _digest("d")},
    ]
    with _client(models) as client:
        result = freeze.freeze_model_set(
            output_directory=tmp_path / "freeze",
            code_commit="abc123",
            client=client,
            now=datetime(2026, 9, 16, 7, 0, tzinfo=UTC),
        )

    assert [item["tag"] for item in result["models"]] == list(
        freeze.REQUIRED_MODEL_TAGS
    )
    assert [item["digest"] for item in result["models"]] == [
        _digest("a"),
        _digest("b"),
        _digest("c"),
    ]
    assert result["market_selection_run"] is False
    assert result["evidence_accessed"] is False
    assert result["model_forecast_run"] is False
    assert result["outcomes_accessed"] is False
    assert result["reserved_holdout_accessed"] is False

    manifest = json.loads(
        (tmp_path / "freeze" / "model-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["code_commit"] == "abc123"
    assert manifest["experiment_id"] == freeze.EXPERIMENT_ID
    assert len(result["model_manifest_sha256"]) == 64


def test_missing_model_fails_before_selection_artifact(tmp_path: Path) -> None:
    models = [
        {"name": "llama3.1:8b", "digest": _digest("a")},
        {"name": "qwen3.5:9b", "digest": _digest("b")},
    ]
    with _client(models) as client, pytest.raises(
        freeze.ModelFreezeError, match="deepseek-r1:8b"
    ):
        freeze.freeze_model_set(
            output_directory=tmp_path / "freeze",
            code_commit="abc123",
            client=client,
        )


def test_rejects_short_digest(tmp_path: Path) -> None:
    models = [
        {"name": "llama3.1:8b", "digest": "46e0c10c039e"},
        {"name": "qwen3.5:9b", "digest": _digest("b")},
        {"name": "deepseek-r1:8b", "digest": _digest("c")},
    ]
    with _client(models) as client, pytest.raises(
        freeze.ModelFreezeError, match="Invalid Ollama model digest"
    ):
        freeze.freeze_model_set(
            output_directory=tmp_path / "freeze",
            code_commit="abc123",
            client=client,
        )


def test_refuses_to_overwrite_existing_freeze(tmp_path: Path) -> None:
    output = tmp_path / "freeze"
    output.mkdir()
    with pytest.raises(freeze.ModelFreezeError, match="Refusing to replace"):
        freeze.freeze_model_set(output_directory=output, code_commit="abc123")
