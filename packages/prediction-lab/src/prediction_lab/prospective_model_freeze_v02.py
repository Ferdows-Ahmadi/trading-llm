"""Freeze exact local Ollama model identities before prospective v0.2 selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

EXPERIMENT_ID = "prospective-live-multimodel-v0.2"
REQUIRED_MODEL_TAGS = (
    "llama3.1:8b",
    "qwen3.5:9b",
    "deepseek-r1:8b",
)


class ModelFreezeError(RuntimeError):
    """Raised when the prospective model-set freeze cannot be completed safely."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _iso_z(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _valid_digest(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("sha256:"):
        hex_value = text.removeprefix("sha256:")
    else:
        hex_value = text
    if len(hex_value) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in hex_value):
        raise ModelFreezeError(f"Invalid Ollama model digest: {text!r}")
    return "sha256:" + hex_value.lower()


def freeze_model_set(
    *,
    output_directory: Path,
    code_commit: str,
    base_url: str = "http://127.0.0.1:11434",
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Freeze exact digests for the three predeclared local model tags."""
    if output_directory.exists():
        raise ModelFreezeError("Refusing to replace existing model-freeze output")
    output_directory.mkdir(parents=True)

    owns_client = client is None
    http = client or httpx.Client(timeout=30.0, follow_redirects=False)
    try:
        try:
            response = http.get(f"{base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelFreezeError(f"Cannot query local Ollama model registry: {exc}") from exc

        raw = response.content
        (output_directory / "ollama-tags.json").write_bytes(raw)
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ModelFreezeError("Ollama /api/tags returned malformed JSON") from exc
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise ModelFreezeError("Ollama /api/tags is missing a models list")

        by_name: dict[str, dict[str, Any]] = {}
        for item in models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                by_name[str(item["name"])] = item

        frozen_models: list[dict[str, str]] = []
        for tag in REQUIRED_MODEL_TAGS:
            item = by_name.get(tag)
            if item is None:
                raise ModelFreezeError(f"Required local Ollama model is missing: {tag}")
            frozen_models.append(
                {
                    "tag": tag,
                    "digest": _valid_digest(item.get("digest")),
                }
            )

        frozen_at = now or datetime.now(UTC)
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "experiment_id": EXPERIMENT_ID,
            "stage": "preselection-model-freeze",
            "code_commit": code_commit,
            "frozen_at": _iso_z(frozen_at),
            "models": frozen_models,
            "ollama_tags_sha256": _sha256(raw),
            "market_selection_run": False,
            "evidence_accessed": False,
            "model_forecast_run": False,
            "outcomes_accessed": False,
            "reserved_holdout_accessed": False,
        }
        manifest_bytes = _canonical_bytes(manifest)
        (output_directory / "model-manifest.json").write_bytes(manifest_bytes)
        receipt = {
            "model_manifest_sha256": _sha256(manifest_bytes),
            "models": frozen_models,
            "frozen_at": manifest["frozen_at"],
        }
        (output_directory / "model-freeze-receipt.json").write_bytes(
            _canonical_bytes(receipt)
        )
        return {**manifest, **receipt}
    finally:
        if owns_client:
            http.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    result = freeze_model_set(
        output_directory=args.output_directory,
        code_commit=args.code_commit,
        base_url=args.ollama_base_url,
    )
    safe = {
        "experiment_id": result["experiment_id"],
        "frozen_at": result["frozen_at"],
        "models": result["models"],
        "model_manifest_sha256": result["model_manifest_sha256"],
        "market_selection_run": result["market_selection_run"],
        "evidence_accessed": result["evidence_accessed"],
        "model_forecast_run": result["model_forecast_run"],
        "outcomes_accessed": result["outcomes_accessed"],
        "reserved_holdout_accessed": result["reserved_holdout_accessed"],
    }
    print(json.dumps(safe, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
