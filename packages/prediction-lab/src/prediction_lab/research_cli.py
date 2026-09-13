from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.experiments import run_development_experiment
from prediction_lab.ollama_adapter import OllamaStructuredModelAdapter
from prediction_lab.research_forecaster import (
    DeterministicFakeModelAdapter,
    StructuredModelAdapter,
)
from prediction_lab.research_types import ModelMetadata, ResearchContractError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a fixture-backed research forecast on a verified development dataset."
    )
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("evidence_fixture", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--prompt-version", default="research-v0")
    parser.add_argument("--mode", choices=("blind", "market-aware"), default="blind")
    parser.add_argument("--validation-fraction", type=float)
    parser.add_argument("--parent-group-column", default="event_id")
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--adapter", choices=("fake", "ollama"), default="fake")
    parser.add_argument("--ollama-model")
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--model-metadata", type=Path)
    return parser


def _load_model_metadata(path: Path) -> ModelMetadata:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchContractError(f"Cannot load model metadata {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ResearchContractError("Model metadata file must contain a JSON object")
    return ModelMetadata.from_dict(payload)


def _build_adapter(args: argparse.Namespace) -> StructuredModelAdapter:
    if args.adapter == "fake":
        if args.ollama_model or args.model_metadata:
            raise ResearchContractError(
                "Ollama model options cannot be supplied when --adapter=fake"
            )
        return DeterministicFakeModelAdapter()

    if not args.ollama_model:
        raise ResearchContractError("--adapter=ollama requires --ollama-model")
    if args.model_metadata is None:
        raise ResearchContractError("--adapter=ollama requires --model-metadata")
    metadata = _load_model_metadata(args.model_metadata)
    return OllamaStructuredModelAdapter(
        model=args.ollama_model,
        metadata=metadata,
        base_url=args.ollama_base_url,
        timeout_seconds=args.ollama_timeout_seconds,
    )


def main() -> None:
    args = _build_parser().parse_args()
    adapter = _build_adapter(args)
    try:
        summary, report_path = run_development_experiment(
            development_csv=args.development_csv,
            development_manifest=args.development_manifest,
            evidence_provider=FileEvidenceProvider(args.evidence_fixture),
            adapter=adapter,
            output_directory=args.output_directory,
            experiment_id=args.experiment_id,
            hypothesis=args.hypothesis,
            prompt_version=args.prompt_version,
            mode=args.mode,
            validation_fraction=args.validation_fraction,
            parent_group_column=args.parent_group_column,
            repository_root=args.repository_root,
        )
    finally:
        if isinstance(adapter, OllamaStructuredModelAdapter):
            adapter.close()
    print(
        json.dumps(
            {
                "execution": summary["execution"],
                "report_path": str(report_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
