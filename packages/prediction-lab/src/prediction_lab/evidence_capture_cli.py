from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.capture_index_client import CaptureIndexCommonCrawlClient
from prediction_lab.evidence_capture_stage import run_commoncrawl_capture_stage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve exact pre-cutoff Common Crawl captures without WARC downloads."
    )
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("discovery_jsonl", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--pilot-size", type=int, default=20)
    parser.add_argument("--max-urls-per-question", type=int, default=6)
    parser.add_argument("--max-collections", type=int, default=3)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--retry-backoff-seconds", type=float, default=2.0)
    parser.add_argument("--minimum-interval-seconds", type=float, default=2.0)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    with CaptureIndexCommonCrawlClient(
        retries=args.retries,
        timeout_seconds=args.timeout_seconds,
        retry_backoff_seconds=args.retry_backoff_seconds,
        minimum_interval_seconds=args.minimum_interval_seconds,
    ) as archive:
        summary, _ = run_commoncrawl_capture_stage(
            development_csv=args.development_csv,
            development_manifest=args.development_manifest,
            discovery_jsonl=args.discovery_jsonl,
            output_directory=args.output_directory,
            archive=archive,
            pilot_size=args.pilot_size,
            max_urls_per_question=args.max_urls_per_question,
            max_collections=args.max_collections,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
