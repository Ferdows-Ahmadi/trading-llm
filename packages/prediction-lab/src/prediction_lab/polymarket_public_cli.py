from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from prediction_lab.benchmark import choose_temporal_holdout_start
from prediction_lab.datasets import freeze_cases, temporal_question_split
from prediction_lab.polymarket_public import (
    PolymarketPublicClient,
    collect_public_polymarket_cases,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a reproducible fixed-lead Polymarket benchmark from public APIs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/prediction-lab/polymarket-public-v0.1"),
    )
    parser.add_argument("--max-questions", type=int, default=300)
    parser.add_argument("--candidate-multiplier", type=int, default=3)
    parser.add_argument("--minimum-lead", default="7D")
    parser.add_argument("--minimum-volume", type=float, default=100.0)
    parser.add_argument("--holdout-fraction", type=float, default=0.25)
    parser.add_argument("--max-market-pages", type=int, default=12)
    return parser


def _stable_jsonl(records: list[dict[str, Any]]) -> bytes:
    lines = [json.dumps(record, sort_keys=True, separators=(",", ":")) for record in records]
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def _write_raw_records(path: Path, records: list[dict[str, Any]]) -> str:
    payload = _stable_jsonl(records)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    args = _build_parser().parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)

    with PolymarketPublicClient() as client:
        cases, acquisition, markets_used, trades_used = collect_public_polymarket_cases(
            client,
            max_questions=args.max_questions,
            candidate_multiplier=args.candidate_multiplier,
            minimum_lead=args.minimum_lead,
            minimum_volume=args.minimum_volume,
            max_market_pages=args.max_market_pages,
        )

    markets_sha = _write_raw_records(output / "source-markets.jsonl", markets_used)
    trades_sha = _write_raw_records(output / "source-trades.jsonl", trades_used)

    holdout_start = choose_temporal_holdout_start(
        cases,
        holdout_fraction=args.holdout_fraction,
    )
    development, holdout = temporal_question_split(cases, holdout_start=holdout_start)

    source_revision = (
        "polymarket-public-api;"
        f"markets-sha256={markets_sha};trades-sha256={trades_sha}"
    )
    selection_policy = (
        f"latest public trade at least {args.minimum_lead} before actual closedTime; "
        f"minimum_volume={args.minimum_volume}; max_questions={args.max_questions}; "
        f"holdout_fraction={args.holdout_fraction}; holdout_start={holdout_start.isoformat()}"
    )

    manifests = {}
    for name, frame in (("development", development), ("holdout", holdout)):
        manifest = freeze_cases(
            frame,
            csv_path=output / f"{name}.csv",
            manifest_path=output / f"{name}.manifest.json",
            source_name="Polymarket Gamma + Data public APIs",
            source_revision=source_revision,
            selection_policy=selection_policy,
        )
        manifests[name] = manifest.to_dict()

    summary = {
        "acquisition": acquisition.to_dict(),
        "holdout_start": holdout_start.isoformat(),
        "development_rows": len(development),
        "holdout_rows": len(holdout),
        "raw_source_hashes": {
            "source-markets.jsonl": markets_sha,
            "source-trades.jsonl": trades_sha,
        },
        "manifests": manifests,
    }
    text = json.dumps(summary, indent=2, sort_keys=True)
    (output / "acquisition-summary.json").write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
