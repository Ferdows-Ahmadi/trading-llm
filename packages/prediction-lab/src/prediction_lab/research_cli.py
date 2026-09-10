from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.experiments import run_development_experiment
from prediction_lab.research_forecaster import DeterministicFakeModelAdapter


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
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    summary, report_path = run_development_experiment(
        development_csv=args.development_csv,
        development_manifest=args.development_manifest,
        evidence_provider=FileEvidenceProvider(args.evidence_fixture),
        adapter=DeterministicFakeModelAdapter(),
        output_directory=args.output_directory,
        experiment_id=args.experiment_id,
        hypothesis=args.hypothesis,
        prompt_version=args.prompt_version,
        mode=args.mode,
        validation_fraction=args.validation_fraction,
        parent_group_column=args.parent_group_column,
        repository_root=args.repository_root,
    )
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
