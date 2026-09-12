from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path

from prediction_lab.research_types import EvidenceItem, ResearchContractError, content_hash

METHOD_VERSION = "lexical-relevance-v2"
DEFAULT_LEAD_WORDS = 40
DEFAULT_INTENT_WINDOW_WORDS = 50
DEFAULT_MIN_BODY_SUBJECT_MENTIONS = 2

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

_ROUNDUP_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("top_n", re.compile(r"\btop\s+\d+\b", re.IGNORECASE)),
    (
        "n_items_to_watch",
        re.compile(
            r"\b\d+\s+(?:crypto|cryptos|tokens?|coins?|projects?)\s+to\s+watch\b",
            re.IGNORECASE,
        ),
    ),
    (
        "periodic_roundup",
        re.compile(
            r"\b(?:daily|weekly|market|crypto)\s+(?:market\s+)?roundup\b",
            re.IGNORECASE,
        ),
    ),
    ("key_crypto_updates", re.compile(r"\bkey\s+crypto\s+updates?\b", re.IGNORECASE)),
)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _title_fingerprint(value: str) -> str:
    return re.sub(r"[\W_]+", " ", _normalize(value), flags=re.UNICODE).strip()


def _word_tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+|[$%]", _normalize(value), flags=re.UNICODE))


def _subsequence_starts(tokens: tuple[str, ...], needle: tuple[str, ...]) -> tuple[int, ...]:
    if not needle or len(needle) > len(tokens):
        return ()
    width = len(needle)
    return tuple(
        index
        for index in range(len(tokens) - width + 1)
        if tokens[index : index + width] == needle
    )


def _contains_subsequence(tokens: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    return bool(_subsequence_starts(tokens, needle))


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


def _roundup_pattern(title: str) -> str | None:
    for name, pattern in _ROUNDUP_TITLE_PATTERNS:
        if pattern.search(title):
            return name
    return None


def _intent_signals_near_subject(
    *,
    title_tokens: tuple[str, ...],
    body_tokens: tuple[str, ...],
    subject_tokens: tuple[str, ...],
    intent: str,
    intent_window_words: int,
) -> tuple[str, ...]:
    combined = title_tokens + body_tokens
    subject_starts = _subsequence_starts(combined, subject_tokens)
    if not subject_starts:
        return ()

    signal_tokens = {
        signal: _word_tokens(signal) for signal in _INTENT_SIGNALS[intent]
    }
    hits: set[str] = set()
    for start in subject_starts:
        left = max(0, start - intent_window_words)
        right = min(
            len(combined),
            start + len(subject_tokens) + intent_window_words,
        )
        window = combined[left:right]
        for signal, tokens in signal_tokens.items():
            if tokens and _contains_subsequence(window, tokens):
                hits.add(signal)
    return tuple(sorted(hits))


def _assess_item(
    item: EvidenceItem,
    *,
    subject: str,
    intent: str,
    lead_words: int,
    intent_window_words: int,
    min_body_subject_mentions: int,
) -> tuple[tuple[str, ...], bool, bool, int, str | None, str | None]:
    subject_tokens = _word_tokens(subject)
    title_tokens = _word_tokens(item.title)
    body_tokens = _word_tokens(item.text)
    if not subject_tokens:
        raise ResearchContractError(f"Question subject has no lexical tokens: {subject!r}")

    title_hit = _contains_subsequence(title_tokens, subject_tokens)
    body_starts = _subsequence_starts(body_tokens, subject_tokens)
    body_mentions = len(body_starts)
    lead_text = " ".join(item.text.split()[:lead_words])
    lead_hit = _contains_subsequence(_word_tokens(lead_text), subject_tokens)
    roundup_match = _roundup_pattern(item.title)

    if not title_hit and body_mentions == 0:
        return (), title_hit, lead_hit, body_mentions, roundup_match, "subject_not_found"
    if roundup_match is not None:
        return (), title_hit, lead_hit, body_mentions, roundup_match, "roundup_or_listicle"
    if not title_hit and not lead_hit:
        return (), title_hit, lead_hit, body_mentions, roundup_match, "subject_not_prominent"
    if not title_hit and body_mentions < min_body_subject_mentions:
        return (
            (),
            title_hit,
            lead_hit,
            body_mentions,
            roundup_match,
            "insufficient_subject_mentions",
        )

    signals = _intent_signals_near_subject(
        title_tokens=title_tokens,
        body_tokens=body_tokens,
        subject_tokens=subject_tokens,
        intent=intent,
        intent_window_words=intent_window_words,
    )
    if not signals:
        return (
            (),
            title_hit,
            lead_hit,
            body_mentions,
            roundup_match,
            "no_intent_signal_near_subject",
        )

    return signals, title_hit, lead_hit, body_mentions, roundup_match, None


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
    lead_words: int = DEFAULT_LEAD_WORDS,
    intent_window_words: int = DEFAULT_INTENT_WINDOW_WORDS,
    min_body_subject_mentions: int = DEFAULT_MIN_BODY_SUBJECT_MENTIONS,
) -> dict[str, object]:
    """Derive a label-blind, deterministic structural relevance evidence fixture."""
    if max_items_per_question < 1:
        raise ValueError("max_items_per_question must be positive")
    if lead_words < 1:
        raise ValueError("lead_words must be positive")
    if intent_window_words < 1:
        raise ValueError("intent_window_words must be positive")
    if min_body_subject_mentions < 1:
        raise ValueError("min_body_subject_mentions must be positive")

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
        candidates: list[
            tuple[bool, bool, int, EvidenceItem, tuple[str, ...]]
        ] = []
        decisions: dict[str, dict[str, object]] = {}
        for raw_item in raw_items:
            item = EvidenceItem.from_dict(raw_item)
            raw_item_count += 1
            (
                signals,
                title_hit,
                lead_hit,
                body_mentions,
                roundup_match,
                reject_reason,
            ) = _assess_item(
                item,
                subject=subject,
                intent=intent,
                lead_words=lead_words,
                intent_window_words=intent_window_words,
                min_body_subject_mentions=min_body_subject_mentions,
            )
            decisions[item.source_id] = {
                "available_at": item.available_at.isoformat(),
                "body_subject_mentions": body_mentions,
                "intent": intent,
                "intent_signal_hits": ";".join(signals),
                "kept": False,
                "lead_subject_match": lead_hit,
                "question_id": question_id,
                "reason": reject_reason or "candidate",
                "roundup_pattern": roundup_match or "",
                "source_id": item.source_id,
                "subject": subject,
                "title": item.title,
                "title_subject_match": title_hit,
            }
            if reject_reason is None:
                candidates.append((title_hit, lead_hit, body_mentions, item, signals))

        candidates.sort(
            key=lambda candidate: (
                -int(candidate[0]),
                -int(candidate[1]),
                -candidate[2],
                -candidate[3].available_at.timestamp(),
                candidate[3].source_id,
            )
        )
        seen_titles: set[str] = set()
        seen_content: set[str] = set()
        kept = 0
        for title_hit, lead_hit, body_mentions, item, signals in candidates:
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
                    "body_subject_mentions": body_mentions,
                    "intent_signal_hits": ";".join(signals),
                    "kept": True,
                    "lead_subject_match": lead_hit,
                    "reason": "kept",
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
        "title_subject_match",
        "lead_subject_match",
        "body_subject_mentions",
        "intent_signal_hits",
        "roundup_pattern",
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
        "dropped_items": raw_item_count - kept_items,
        "filtered_fixture_hash": content_hash(filtered_payload),
        "intent_window_words": intent_window_words,
        "kept_items": kept_items,
        "lead_words": lead_words,
        "max_items_per_question": max_items_per_question,
        "method_version": METHOD_VERSION,
        "min_body_subject_mentions": min_body_subject_mentions,
        "pilot_questions": len(pilot_ids),
        "questions_with_kept": questions_with_kept,
        "questions_without_kept": len(pilot_ids) - questions_with_kept,
        "raw_items": raw_item_count,
    }
    _write_json(output / "relevance-summary.json", summary)
    return summary
