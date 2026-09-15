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


def test_filter_v2_is_structural_label_blind_and_preserves_empty_questions(
    tmp_path: Path,
) -> None:
    benchmark = tmp_path / "development.csv"
    questions = (
        ("q1", "Brevis FDV above $1B one day after launch?", "1"),
        ("q2", "Seeker FDV above $600M one day after launch?", "0"),
        ("q3", "Will Titan launch a token by March 31, 2026?", "1"),
        ("q4", "Will Rabby launch a token by March 31, 2026?", "0"),
        ("q5", "Will EdgeX launch a token by September 30, 2026?", "1"),
        ("q6", "Will Zcash dip to $300 by December 31, 2026?", "0"),
        ("q7", "Will Phantom launch a token by March 31, 2026?", "0"),
    )
    with benchmark.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("question_id", "question_text", "outcome"))
        writer.writeheader()
        for question_id, question_text, outcome in questions:
            writer.writerow(
                {
                    "question_id": question_id,
                    "question_text": question_text,
                    "outcome": outcome,
                }
            )

    discovery = tmp_path / "discovery.jsonl"
    discovery.write_text(
        "".join(
            json.dumps({"question_id": question_id}) + "\n"
            for question_id, _, _ in questions
        ),
        encoding="utf-8",
    )

    buried_prefix = " ".join(f"filler{index}" for index in range(45))
    far_prefix = " ".join(f"neutral{index}" for index in range(60))
    fixture = {
        "schema_version": 1,
        "questions": {
            "q1": [
                _item(
                    "a-brevis-good",
                    "Brevis publishes BREV tokenomics",
                    "Brevis disclosed BREV tokenomics before its token launch.",
                ),
                _item(
                    "z-brevis-duplicate-title",
                    "Brevis publishes BREV tokenomics",
                    "Brevis separately discussed tokenomics and its planned launch.",
                ),
            ],
            "q2": [
                _item(
                    "seeker-incidental",
                    "Museum and technology notes",
                    "Seeker appeared once in a long technology note beside token projects.",
                )
            ],
            "q3": [
                _item(
                    "titan-lead",
                    "Protocol roadmap update",
                    (
                        "Titan plans a token launch this spring. "
                        "Titan also published its rollout schedule."
                    ),
                )
            ],
            "q4": [
                _item(
                    "rabby-roundup",
                    "Key Crypto Updates: Rabby token launch and other projects",
                    "Rabby discussed its token launch. Rabby was one of several projects covered.",
                )
            ],
            "q5": [
                _item(
                    "edgex-buried",
                    "Industry notes",
                    f"{buried_prefix} EdgeX plans a token launch. EdgeX published a roadmap.",
                )
            ],
            "q6": [
                _item(
                    "zcash-far-intent",
                    "Zcash project update",
                    f"{far_prefix} price support and resistance were discussed.",
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
        lead_words=40,
        intent_window_words=50,
        min_body_subject_mentions=2,
    )

    assert summary["method_version"] == "lexical-relevance-v2"
    assert summary["pilot_questions"] == 7
    assert summary["raw_items"] == 7
    assert summary["kept_items"] == 2
    assert summary["questions_with_kept"] == 2
    assert summary["questions_without_kept"] == 5
    assert summary["lead_words"] == 40
    assert summary["intent_window_words"] == 50
    assert summary["min_body_subject_mentions"] == 2

    filtered = json.loads(
        (output / "evidence-fixture.filtered.json").read_text(encoding="utf-8")
    )
    assert [item["source_id"] for item in filtered["questions"]["q1"]] == [
        "a-brevis-good"
    ]
    assert [item["source_id"] for item in filtered["questions"]["q3"]] == [
        "titan-lead"
    ]
    for question_id in ("q2", "q4", "q5", "q6", "q7"):
        assert filtered["questions"][question_id] == []

    with (output / "relevance-audit.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        audit = {row["source_id"]: row for row in csv.DictReader(handle)}

    assert audit["z-brevis-duplicate-title"]["reason"] == "duplicate_title"
    assert audit["seeker-incidental"]["reason"] == "insufficient_subject_mentions"
    assert audit["rabby-roundup"]["reason"] == "roundup_or_listicle"
    assert audit["rabby-roundup"]["roundup_pattern"] == "key_crypto_updates"
    assert audit["edgex-buried"]["reason"] == "subject_not_prominent"
    assert audit["zcash-far-intent"]["reason"] == "no_intent_signal_near_subject"

    provider = FileEvidenceProvider(output / "evidence-fixture.filtered.json")
    packet = provider.build_packet(
        question_id="q7",
        forecasted_at="2025-12-02T00:00:00Z",
        research_cutoff_at="2025-12-02T00:00:00Z",
    )
    assert packet.evidence_items == ()
