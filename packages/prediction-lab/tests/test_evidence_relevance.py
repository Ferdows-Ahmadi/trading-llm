from __future__ import annotations

import csv
import json
from pathlib import Path

from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.evidence_relevance import extract_question_subject, filter_evidence_fixture
from prediction_lab.research_types import EvidenceItem


def _item(source_id: str, title: str, text: str) -> dict[str, object]:
    return EvidenceItem.create(
        source_id=source_id,
        source_type="wayback-archived-news",
        uri_or_reference=f"https://example.org/{source_id}",
        title=title,
        available_at="2025-12-01T00:00:00Z",
        retrieved_at="2026-09-01T00:00:00Z",
        text=text,
    ).to_dict()


def test_extract_question_subject_for_supported_pilot_shapes() -> None:
    assert extract_question_subject("Brevis FDV above $1B one day after launch?") == (
        "Brevis",
        "fdv",
    )
    assert extract_question_subject("Zama auction clearing price above $0.07?") == (
        "Zama",
        "auction",
    )
    assert extract_question_subject("Will Zcash dip to $300 by December 31, 2026?") == (
        "Zcash",
        "dip",
    )
    assert extract_question_subject("Will EdgeX launch a token by September 30, 2026?") == (
        "EdgeX",
        "token_launch",
    )


def test_filter_is_label_blind_conservative_and_keeps_empty_questions(tmp_path: Path) -> None:
    benchmark = tmp_path / "development.csv"
    with benchmark.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("question_id", "question_text", "outcome"))
        writer.writeheader()
        writer.writerows(
            (
                {
                    "question_id": "q1",
                    "question_text": "Brevis FDV above $1B one day after launch?",
                    "outcome": "1",
                },
                {
                    "question_id": "q2",
                    "question_text": "Seeker FDV above $600M one day after launch?",
                    "outcome": "0",
                },
                {
                    "question_id": "q3",
                    "question_text": "Will Titan launch a token by March 31, 2026?",
                    "outcome": "1",
                },
                {
                    "question_id": "q4",
                    "question_text": "Will Rabby launch a token by March 31, 2026?",
                    "outcome": "0",
                },
            )
        )

    discovery = tmp_path / "discovery.jsonl"
    discovery.write_text(
        "".join(json.dumps({"question_id": question_id}) + "\n" for question_id in ("q1", "q2", "q3", "q4")),
        encoding="utf-8",
    )
    fixture = {
        "schema_version": 1,
        "questions": {
            "q1": [
                _item(
                    "brevis-good",
                    "Brevis publishes BREV tokenomics",
                    "Brevis disclosed BREV tokenomics before its token launch.",
                ),
                _item(
                    "brevis-duplicate-title",
                    "Brevis publishes BREV tokenomics",
                    "A syndicated copy says Brevis disclosed tokenomics before launch.",
                ),
            ],
            "q2": [
                _item(
                    "seeker-noise",
                    "Dolly Parton exhibition",
                    "The museum opened Dolly Parton: Journey of a Seeker in Nashville.",
                )
            ],
            "q3": [
                _item(
                    "titan-noise",
                    "The Sandbox announces a game",
                    "Attack on Titan avatars appear among NFT collections in The Sandbox.",
                )
            ],
        },
    }
    fixture_path = tmp_path / "evidence.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    output = tmp_path / "filtered"
    summary = filter_evidence_fixture(
        benchmark_csv=benchmark,
        discovery_jsonl=discovery,
        evidence_fixture=fixture_path,
        output_directory=output,
        max_items_per_question=5,
        context_chars=260,
    )

    assert summary["pilot_questions"] == 4
    assert summary["raw_items"] == 4
    assert summary["kept_items"] == 1
    assert summary["questions_with_kept"] == 1
    assert summary["questions_without_kept"] == 3

    filtered = json.loads(
        (output / "evidence-fixture.filtered.json").read_text(encoding="utf-8")
    )
    assert list(filtered["questions"]["q1"])[0]["source_id"] == "brevis-good"
    assert filtered["questions"]["q2"] == []
    assert filtered["questions"]["q3"] == []
    assert filtered["questions"]["q4"] == []

    provider = FileEvidenceProvider(output / "evidence-fixture.filtered.json")
    packet = provider.build_packet(
        question_id="q4",
        forecasted_at="2025-12-02T00:00:00Z",
        research_cutoff_at="2025-12-02T00:00:00Z",
    )
    assert packet.evidence_items == ()
