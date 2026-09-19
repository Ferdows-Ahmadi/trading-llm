from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.commoncrawl_evidence import CommonCrawlClient, build_commoncrawl_pilot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a timestamp-safe Common Crawl evidence pilot from frozen "
            "development data."
        )
    )
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("source_markets_jsonl", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--pilot-size", type=int, default=20)
    parser.add_argument("--max-reference-urls", type=int, default=3)
    parser.add_argument("--max-evidence-items", type=int, default=2)
    parser.add_argument("--max-collections", type=int, default=6)
    parser.add_argument("--max-characters-per-item", type=int, default=12000)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    output = args.output_directory
    output.mkdir(parents=True, exist_ok=True)

    with CommonCrawlClient() as client:
        fixture, summary, audit = build_commoncrawl_pilot(
            development_csv=args.development_csv,
            development_manifest=args.development_manifest,
            source_markets_jsonl=args.source_markets_jsonl,
            client=client,
            pilot_size=args.pilot_size,
            max_reference_urls=args.max_reference_urls,
            max_evidence_items=args.max_evidence_items,
            max_collections=args.max_collections,
            max_characters_per_item=args.max_characters_per_item,
        )

    (output / "evidence-fixture.json").write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "evidence-pilot-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    audit.to_csv(
        output / "evidence-pilot-audit.csv",
        index=False,
        lineterminator="\n",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
