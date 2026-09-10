from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

from prediction_lab.research_types import EvidenceItem, ResearchContractError, content_hash

METHOD_VERSION = "lexical-relevance-v1"

_INTENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?P<subject>.+?)\s+FDV\b", re.IGNORECASE), "fdv"),
    (re.compile(r"^(?P<subject>.+?)\s+auction\b", re.IGNORECASE), "auction"),
    (re.compile(r"^Will\s+(?P<subject>.+?)\s+dip\b", re.IGNORECASE), "dip"),
    (
        re.compile(
            r"^Will\s+(?P<subject>.+?)\s+launch\s+a\s+token\b",
            re.IGNORECASE,
        ),
        "token_launch",
    ),
)

_INTENT_SIGNALS: dict[str, tuple[str, ...]] = {
    "fdv": (
        "fdv",
        "tokenomics",
        "token sale",
        "token launch",
        "token launches",
        "tge",
        "airdrop",
        "listing",
        "goes live",
        "launch",
        "launched",
        "token",
    ),
    "auction": (
        "auction",
        "community sale",
        "token sale",
        "clearing price",
        "floor price",
        "fdv",
        "sale",
    ),
    "dip": (
        "dip",
        "price",
        "rally",
        "market",
        "trading",
        "support",
        "resistance",
        "high",
        "low",
        "ath",
        "usd",
        "$",
    ),
    "token_launch": (
        "token generation event",
        "tge",
        "tokenomics",
        "airdrop",
        "token launch",
        "launch a token",
        "launches token",
        "launches its token",
        "token sale",
        "premarket",
        "pre-market",
        "token plans",
        "token debut",
        "token release",
        "goes live on binance futures",
        "goes live on",
    ),
}


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _title_fingerprint(value: str) -> str:
    return re.sub(r"[\W_]+", " ", _normalize(value), flags=re.UNICODE).strip()


def extract_question_subject(question_text: str) -> tuple[str, str]:
    text = question_text.strip()
    for pattern, intent in _INTENT_PATTERNS:
        match = pattern.search(text)
        if match:
            subject = match.group("subject").strip()
            if subject:
                return subject, intent
    raise ResearchContractError(
        f"Unsupported pilot question shape for deterministic relevance filtering: {question_text!r}"
    )


def _subject_positions(text: str, subject: str) -> tuple[str, list[int]]:
    normalized = _normalize(text)
    normalized_subject = _normalize(subject)
    pattern = re.compile(r"(?<![\w])" + re.escape(normalized_subject) + r"(?![\w])")
    return normalized, [match.start() for match in pattern.finditer(normalized)]


def _score_item(
    item: EvidenceItem,
    *,
    subject: str,
    intent: str,
    context_chars: int,
) -> tuple[int, tuple[str, ...], bool, str | None]:
    combined = f"{item.title}\n{item.text}"
    normalized, positions = _subject_positions(combined, subject)
    if not positions:
        return 0, (), False, "subject_not_found"

    normalized_subject = _normalize(subject)
    signals: set[str] = set()
    for position in positions:
        start = max(0, position - context_chars)
        end = position + len(normalized_subject) + context_chars
        window = normalized[start:end]
        for signal in _INTENT_SIGNALS[intent]:
            if signal in window:
                signals.add(signal)

    if not signals:
        return 0, (), False, "no_intent_signal_near_subject"

    _, title_positions = _subject_positions(item.title, subject)
    title_hit = bool(title_positions)
    score = 2 * min(3, len(signals)) + (4 if title_hit else 0)
    return score, tuple(sorted(signals)), title_hit, None


def _read_questions(path: str | Path) -> dict[str, str]:
    questions: dict[str, str] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"question_id", "question_text"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ResearchContractError("Benchmark CSV must contain question_id and question_text")
        for row in reader:
            question_id = str(row.get("question_id") or "").strip()
            question_text = str(row.get("question_text") or "").strip()
            if question_id and question_text:
                questions[question_id] = question_text
    return questions


def _read_pilot_ids(path: str | Path) -> tuple[str, ...]:
    question_ids: list[str] = []
    seen: set[str] = set()
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ResearchContractError(
                f"Malformed discovery JSONL at line {line_number}"
            ) from exc
        if not isinstance(record, dict):
            raise ResearchContractError(
                f"Discovery JSONL line {line_number} must be an object"
            )
        question_id = str(record.get("question_id") or "").strip()
        if not question_id:
            raise ResearchContractError(
                f"Discovery JSONL line {line_number} has no question_id"
            )
        if question_id not in seen:
            seen.add(question_id)
            question_ids.append(question_id)
    return tuple(question_ids)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def filter_evidence_fixture(
    *,
    benchmark_csv: str | Path,
    discovery_jsonl: str | Path,
    evidence_fixture: str | Path,
    output_directory: str | Path,
    max_items_per_question: int = 5,
    context_chars: int = 260,
) -> dict[str, object]:
    """Derive a label-blind, deterministic relevance-filtered historical evidence fixture."""
    if max_items_per_question < 1:
        raise ValueError("max_items_per_question must be positive")
    if context_chars < 50:
        raise ValueError("context_chars must be at least 50")

    questions = _read_questions(benchmark_csv)
    pilot_ids = _read_pilot_ids(discovery_jsonl)
    try:
        fixture_payload = json.loads(Path(evidence_fixture).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchContractError(f"Cannot load evidence fixture: {exc}") from exc
    if not isinstance(fixture_payload, dict) or fixture_payload.get("schema_version") != 1:
        raise ResearchContractError("Evidence fixture must use schema_version 1")
    raw_questions = fixture_payload.get("questions")
    if not isinstance(raw_questions, dict):
        raise ResearchContractError("Evidence fixture questions must be an object")

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    filtered: dict[str, list[dict[str, object]]] = {
        question_id: [] for question_id in pilot_ids
    }
    audit_rows: list[dict[str, object]] = []
    raw_item_count = 0

    for question_id in pilot_ids:
        question_text = questions.get(question_id)
        if question_text is None:
            raise ResearchContractError(
                f"Pilot question {question_id} is absent from benchmark CSV"
            )
        raw_items = raw_questions.get(question_id, [])
        if not isinstance(raw_items, list) or not all(
            isinstance(item, dict) for item in raw_items
        ):
            raise ResearchContractError(
                f"Evidence fixture entry {question_id} must be an item list"
            )
        if not raw_items:
            continue

        subject, intent = extract_question_subject(question_text)
        candidates: list[tuple[int, bool, EvidenceItem, tuple[str, ...]]] = []
        decisions: dict[str, dict[str, object]] = {}
        for raw_item in raw_items:
            item = EvidenceItem.from_dict(raw_item)
            raw_item_count += 1
            score, signals, title_hit, reject_reason = _score_item(
                item,
                subject=subject,
                intent=intent,
                context_chars=context_chars,
            )
            decisions[item.source_id] = {
                "available_at": item.available_at.isoformat(),
                "intent": intent,
                "kept": False,
                "question_id": question_id,
                "reason": reject_reason or "candidate",
                "score": score,
                "signal_hits": ";".join(signals),
                "source_id": item.source_id,
                "subject": subject,
                "title": item.title,
                "title_subject_match": title_hit,
            }
            if reject_reason is None:
                candidates.append((score, title_hit, item, signals))

        candidates.sort(
            key=lambda candidate: (
                -candidate[0],
                -int(candidate[1]),
                -candidate[2].available_at.timestamp(),
                candidate[2].source_id,
            )
        )
        seen_titles: set[str] = set()
        seen_content: set[str] = set()
        kept = 0
        for score, title_hit, item, signals in candidates:
            decision = decisions[item.source_id]
            title_key = _title_fingerprint(item.title)
            if item.content_hash in seen_content:
                decision["reason"] = "duplicate_content"
                continue
            if title_key and title_key in seen_titles:
                decision["reason"] = "duplicate_title"
                continue
            seen_content.add(item.content_hash)
            if title_key:
                seen_titles.add(title_key)
            if kept >= max_items_per_question:
                decision["reason"] = "rank_cap"
                continue
            filtered[question_id].append(item.to_dict())
            kept += 1
            decision.update(
                {
                    "kept": True,
                    "reason": "kept",
                    "score": score,
                    "signal_hits": ";".join(signals),
                    "title_subject_match": title_hit,
                }
            )

        audit_rows.extend(decisions.values())

    filtered_payload = {"questions": filtered, "schema_version": 1}
    filtered_path = output / "evidence-fixture.filtered.json"
    _write_json(filtered_path, filtered_payload)

    audit_fields = (
        "question_id",
        "subject",
        "intent",
        "source_id",
        "available_at",
        "title",
        "score",
        "title_subject_match",
        "signal_hits",
        "kept",
        "reason",
    )
    audit_path = output / "relevance-audit.csv"
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit_fields)
        writer.writeheader()
        writer.writerows(audit_rows)

    kept_items = sum(len(items) for items in filtered.values())
    questions_with_kept = sum(bool(items) for items in filtered.values())
    summary: dict[str, object] = {
        "context_chars": context_chars,
        "dropped_items": raw_item_count - kept_items,
        "filtered_fixture_hash": content_hash(filtered_payload),
        "kept_items": kept_items,
        "max_items_per_question": max_items_per_question,
        "method_version": METHOD_VERSION,
        "pilot_questions": len(pilot_ids),
        "questions_with_kept": questions_with_kept,
        "questions_without_kept": len(pilot_ids) - questions_with_kept,
        "raw_items": raw_item_count,
    }
    _write_json(output / "relevance-summary.json", summary)
    return summary
