from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediction_lab.gdelt_evidence import (
    FastCommonCrawlClient,
    GdeltDocClient,
    build_gdelt_commoncrawl_pilot,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a GDELT-discovered, Common-Crawl-verified historical news pilot."
    )
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--pilot-size", type=int, default=20)
    parser.add_argument("--lookback-days", type=int, default=45)
    parser.add_argument("--max-discovery-records", type=int, default=20)
    parser.add_argument("--max-article-urls", type=int, default=6)
    parser.add_argument("--max-evidence-items", type=int, default=2)
    parser.add_argument("--max-collections", type=int, default=3)
    parser.add_argument("--max-characters-per-item", type=int, default=10000)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    output = args.output_directory
    output.mkdir(parents=True, exist_ok=True)

    with GdeltDocClient() as discovery, FastCommonCrawlClient(retries=2) as archive:
        fixture, summary, audit = build_gdelt_commoncrawl_pilot(
            development_csv=args.development_csv,
            development_manifest=args.development_manifest,
            discovery=discovery,
            archive=archive,
            pilot_size=args.pilot_size,
            lookback_days=args.lookback_days,
            max_discovery_records=args.max_discovery_records,
            max_article_urls=args.max_article_urls,
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
