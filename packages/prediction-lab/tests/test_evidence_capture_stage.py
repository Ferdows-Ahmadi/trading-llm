from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from prediction_lab.commoncrawl_evidence import CommonCrawlCapture
from prediction_lab.datasets import freeze_cases
from prediction_lab.evidence_capture_stage import run_commoncrawl_capture_stage


@dataclass
class FakeArchive:
    calls: int = 0

    def latest_capture_before(
        self,
        url: str,
        *,
        cutoff: object,
        max_collections: int,
    ) -> CommonCrawlCapture | None:
        del max_collections
        self.calls += 1
        cutoff_at = pd.Timestamp(cutoff)
        if "miss" in url:
            return None
        return CommonCrawlCapture(
            crawl_id="CC-MAIN-2025-43",
            timestamp=cutoff_at - pd.Timedelta(hours=2),
            url=url,
            digest=f"digest-{self.calls}",
            filename="crawl-data/example.warc.gz",
            offset=100,
            length=200,
            mime="text/html",
            status="200",
        )


def _freeze_development(tmp_path: Path) -> tuple[Path, Path, Path]:
    rows: list[dict[str, object]] = []
    discovery: list[dict[str, object]] = []
    for index in range(3):
        forecasted = pd.Timestamp("2025-10-01T12:00:00Z") + pd.Timedelta(days=index)
        question_id = f"q-{index}"
        rows.append(
            {
                "question_id": question_id,
                "question_text": f"Will event {index} happen?",
                "forecasted_at": forecasted,
                "resolved_at": forecasted + pd.Timedelta(days=10),
                "market_price_timestamp": forecasted,
                "source_cutoff_at": forecasted,
                "market_probability": 0.5,
                "outcome": index % 2,
                "event_id": f"event-{index}",
                "split": "development",
            }
        )
        discovery.append(
            {
                "question_id": question_id,
                "question_text": f"Will event {index} happen?",
                "event_id": f"event-{index}",
                "forecasted_at": forecasted.isoformat(),
                "source_cutoff_at": forecasted.isoformat(),
                "articles": [
                    {
                        "title": f"Article {index}",
                        "url": (
                            f"https://example.com/{'miss' if index == 2 else 'hit'}/{index}"
                        ),
                        "seen_at": (forecasted - pd.Timedelta(hours=1)).isoformat(),
                    }
                ],
                "article_count": 1,
                "error": None,
            }
        )

    csv_path = tmp_path / "development.csv"
    manifest_path = tmp_path / "development.manifest.json"
    freeze_cases(
        pd.DataFrame(rows),
        csv_path=csv_path,
        manifest_path=manifest_path,
        source_name="test",
        source_revision="test-revision",
        selection_policy="capture stage fixture",
    )
    discovery_path = tmp_path / "discovery.jsonl"
    discovery_path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in discovery),
        encoding="utf-8",
    )
    return csv_path, manifest_path, discovery_path


def test_capture_stage_finds_pre_cutoff_captures_and_reuses_checkpoints(
    tmp_path: Path,
) -> None:
    csv_path, manifest_path, discovery_path = _freeze_development(tmp_path)
    output = tmp_path / "capture-index"
    archive = FakeArchive()

    first_summary, first_audit = run_commoncrawl_capture_stage(
        development_csv=csv_path,
        development_manifest=manifest_path,
        discovery_jsonl=discovery_path,
        output_directory=output,
        archive=archive,
        pilot_size=3,
        max_urls_per_question=2,
        max_collections=2,
    )
    assert archive.calls == 3
    assert first_summary["questions_with_captures"] == 2
    assert first_summary["captures_found"] == 2
    assert first_summary["urls_without_capture"] == 1
    assert first_summary["lookup_failures"] == 0
    assert len(first_audit) == 3

    second_summary, second_audit = run_commoncrawl_capture_stage(
        development_csv=csv_path,
        development_manifest=manifest_path,
        discovery_jsonl=discovery_path,
        output_directory=output,
        archive=archive,
        pilot_size=3,
        max_urls_per_question=2,
        max_collections=2,
    )
    assert archive.calls == 3
    assert second_summary["attempted_this_run"] == 0
    assert second_summary["reused_checkpoints"] == 3
    assert second_audit.equals(first_audit)
    assert (output / "captures.jsonl").exists()
