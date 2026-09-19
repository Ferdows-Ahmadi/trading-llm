from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from prediction_lab import prospective_model_freeze_v03 as freeze

DIGESTS = {
    "llama3.1:8b": "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
    "qwen3.5:9b": "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7",
    "deepseek-r1:8b": "6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763",
}


def _client(models: dict[str, str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": name, "digest": f"sha256:{digest}"}
                    for name, digest in models.items()
                ]
            },
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_v03_freeze_writes_exact_reproducible_identities(tmp_path) -> None:
    http = _client(DIGESTS)
    result = freeze.freeze_model_set(
        output_directory=tmp_path / "freeze",
        code_commit="abc123",
        client=http,
        now=datetime(2026, 9, 17, 8, 30, tzinfo=UTC),
    )
    assert result["experiment_id"] == "prospective-live-source-routing-v0.3"
    assert result["market_selection_run"] is False
    assert result["evidence_accessed"] is False
    assert result["model_forecast_run"] is False
    assert result["outcomes_accessed"] is False
    assert result["reserved_holdout_accessed"] is False
    assert result["models"] == [
        {"tag": tag, "digest": f"sha256:{DIGESTS[tag]}"}
        for tag in freeze.REQUIRED_MODEL_TAGS
    ]
    manifest = json.loads(
        (tmp_path / "freeze" / "model-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["code_commit"] == "abc123"
    assert manifest["frozen_at"] == "2026-09-17T08:30:00Z"
    receipt = json.loads(
        (tmp_path / "freeze" / "model-freeze-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["model_manifest_sha256"] == result["model_manifest_sha256"]
    http.close()


def test_v03_freeze_rejects_missing_required_model(tmp_path) -> None:
    models = dict(DIGESTS)
    models.pop("deepseek-r1:8b")
    http = _client(models)
    with pytest.raises(freeze.ModelFreezeError, match="deepseek-r1:8b"):
        freeze.freeze_model_set(
            output_directory=tmp_path / "freeze",
            code_commit="abc123",
            client=http,
        )
    http.close()


def test_v03_freeze_refuses_overwrite(tmp_path) -> None:
    output = tmp_path / "freeze"
    http = _client(DIGESTS)
    freeze.freeze_model_set(
        output_directory=output,
        code_commit="abc123",
        client=http,
    )
    with pytest.raises(freeze.ModelFreezeError, match="Refusing to replace"):
        freeze.freeze_model_set(
            output_directory=output,
            code_commit="abc123",
            client=http,
        )
    http.close()
