from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.wayback_content import WaybackReplayClient, freeze_wayback_content


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch verified Wayback snapshots and freeze historical evidence content."
    )
    parser.add_argument("captures_jsonl", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--max-items-per-question", type=int, default=1)
    parser.add_argument("--minimum-text-chars", type=int, default=200)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--retry-backoff-seconds", type=float, default=3.0)
    parser.add_argument("--minimum-interval-seconds", type=float, default=2.0)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    with WaybackReplayClient(
        retries=args.retries,
        timeout_seconds=args.timeout_seconds,
        retry_backoff_seconds=args.retry_backoff_seconds,
        minimum_interval_seconds=args.minimum_interval_seconds,
    ) as replay_client:
        summary = freeze_wayback_content(
            captures_jsonl=args.captures_jsonl,
            output_directory=args.output_directory,
            replay_client=replay_client,
            max_items_per_question=args.max_items_per_question,
            minimum_text_chars=args.minimum_text_chars,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
