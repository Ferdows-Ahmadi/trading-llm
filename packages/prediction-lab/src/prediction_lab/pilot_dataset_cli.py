from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.pilot_dataset import build_development_pilot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze the development rows selected by a frozen discovery pilot."
    )
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("discovery_jsonl", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument("--expected-question-count", type=int)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    manifest = build_development_pilot(
        development_csv=args.development_csv,
        development_manifest=args.development_manifest,
        discovery_jsonl=args.discovery_jsonl,
        output_csv=args.output_csv,
        output_manifest=args.output_manifest,
        expected_question_count=args.expected_question_count,
    )
    print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
