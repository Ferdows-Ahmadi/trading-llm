from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.evidence_relevance import filter_evidence_fixture


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Filter frozen historical evidence with a deterministic, label-blind "
            "structural relevance rule."
        )
    )
    parser.add_argument("benchmark_csv", type=Path)
    parser.add_argument("discovery_jsonl", type=Path)
    parser.add_argument("evidence_fixture", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--max-items-per-question", type=int, default=5)
    parser.add_argument("--lead-words", type=int, default=40)
    parser.add_argument("--intent-window-words", type=int, default=50)
    parser.add_argument("--min-body-subject-mentions", type=int, default=2)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    summary = filter_evidence_fixture(
        benchmark_csv=args.benchmark_csv,
        discovery_jsonl=args.discovery_jsonl,
        evidence_fixture=args.evidence_fixture,
        output_directory=args.output_directory,
        max_items_per_question=args.max_items_per_question,
        lead_words=args.lead_words,
        intent_window_words=args.intent_window_words,
        min_body_subject_mentions=args.min_body_subject_mentions,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
