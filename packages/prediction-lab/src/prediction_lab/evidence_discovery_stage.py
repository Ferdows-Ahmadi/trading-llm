from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

import pandas as pd

from prediction_lab.commoncrawl_evidence import HistoricalEvidenceError, select_parent_event_pilot
from prediction_lab.datasets import verify_frozen_dataset
from prediction_lab.gdelt_evidence import GdeltArticle


class DiscoveryProvider(Protocol):
    def search(
        self,
        question_text: str,
        *,
        cutoff: pd.Timestamp,
        lookback_days: int,
        max_records: int,
    ) -> list[GdeltArticle]: ...


def _checkpoint_name(question_id: str) -> str:
    digest = hashlib.sha256(question_id.encode("utf-8")).hexdigest()
    return f"{digest}.json"


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _article_dict(article: GdeltArticle) -> dict[str, object]:
    payload = asdict(article)
    payload["seen_at"] = article.seen_at.isoformat()
    return payload


def run_gdelt_discovery_stage(
    *,
    development_csv: str | Path,
    development_manifest: str | Path,
    output_directory: str | Path,
    discovery: DiscoveryProvider,
    pilot_size: int = 20,
    lookback_days: int = 45,
    max_records: int = 20,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Run a development-only, resumable GDELT discovery pilot.

    Each question is checkpointed atomically as soon as its discovery attempt finishes.
    Successful checkpoints are reused. Failed checkpoints are retried and atomically
    replaced so transient provider errors do not become permanently cached failures.
    Selection and search construction never consult outcomes or market probabilities.
    """

    if pilot_size < 1:
        raise ValueError("pilot_size must be positive")
    if lookback_days < 1:
        raise ValueError("lookback_days must be positive")
    if not 1 <= max_records <= 250:
        raise ValueError("max_records must be between 1 and 250")

    development = verify_frozen_dataset(
        csv_path=development_csv,
        manifest_path=development_manifest,
    )
    split_values = set(development.get("split", pd.Series(dtype=str)).astype(str))
    if split_values != {"development"}:
        raise HistoricalEvidenceError("Discovery stage accepts development rows only")

    pilot = select_parent_event_pilot(development, size=pilot_size)
    output = Path(output_directory)
    checkpoints = output / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    reused = 0
    retried_failed = 0
    attempted = 0

    for row in pilot.itertuples(index=False):
        question_id = str(row.question_id)
        checkpoint = checkpoints / _checkpoint_name(question_id)
        if checkpoint.exists():
            cached = json.loads(checkpoint.read_text(encoding="utf-8"))
            cached_error = str(cached.get("error") or "").strip()
            if not cached_error:
                records.append(cached)
                reused += 1
                continue
            retried_failed += 1

        attempted += 1
        cutoff = pd.Timestamp(row.source_cutoff_at)
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize("UTC")
        else:
            cutoff = cutoff.tz_convert("UTC")

        error: str | None = None
        articles: list[GdeltArticle] = []
        try:
            articles = discovery.search(
                str(row.question_text),
                cutoff=cutoff,
                lookback_days=lookback_days,
                max_records=max_records,
            )
        except Exception as exc:  # noqa: BLE001 - network/provider failure is data here
            error = f"{type(exc).__name__}: {exc}"

        record: dict[str, object] = {
            "question_id": question_id,
            "question_text": str(row.question_text),
            "event_id": str(row.event_id),
            "forecasted_at": pd.Timestamp(row.forecasted_at).isoformat(),
            "source_cutoff_at": cutoff.isoformat(),
            "articles": [_article_dict(article) for article in articles],
            "article_count": len(articles),
            "error": error,
        }
        _atomic_write_json(checkpoint, record)
        records.append(record)

    records.sort(key=lambda item: (str(item["forecasted_at"]), str(item["question_id"])))
    output.mkdir(parents=True, exist_ok=True)
    discovery_jsonl = output / "discovery.jsonl"
    discovery_jsonl.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )

    audit = pd.DataFrame(
        {
            "question_id": [record["question_id"] for record in records],
            "event_id": [record["event_id"] for record in records],
            "article_count": [record["article_count"] for record in records],
            "error": [record["error"] or "" for record in records],
        }
    )
    audit.to_csv(output / "discovery-audit.csv", index=False, lineterminator="\n")

    questions_with_results = sum(int(record["article_count"]) > 0 for record in records)
    failures = sum(bool(record["error"]) for record in records)
    total_articles = sum(int(record["article_count"]) for record in records)
    summary: dict[str, object] = {
        "pilot_questions": len(records),
        "questions_with_results": questions_with_results,
        "questions_without_results": len(records) - questions_with_results,
        "provider_failures": failures,
        "total_articles": total_articles,
        "attempted_this_run": attempted,
        "reused_checkpoints": reused,
        "retried_failed_checkpoints": retried_failed,
        "lookback_days": lookback_days,
        "max_records": max_records,
    }
    _atomic_write_json(output / "discovery-summary.json", summary)
    return summary, audit
