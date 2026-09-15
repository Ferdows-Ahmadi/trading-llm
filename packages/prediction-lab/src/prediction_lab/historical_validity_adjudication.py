"""Freeze the preregistered A/B/C historical-validity audit for 64 dev cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

CANDIDATE_SHA = "6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21"
DEVELOPMENT_SHA = "c05cbfa404804789faec779877c839b6655abc317217f182a673b2e91bd9f9a7"
SOURCE_ID = 10320984640
SOURCE_DIGEST = (
    "sha256:aee2e398b421bd8b2a94fbfd3f5edf2c6fb28c2b71f490e8a98c60ee3b8c7648"
)
SOURCE_CODE = "70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2"
PROTOCOL_COMMIT = "e42d53029b41392c74281c9fa669fb7fc433ad32"
EVIDENCE_COMMIT = "92f77c29817928c26eec6a6c6eaed13b0fd6e9ee"
A_VERIFIED = frozenset({"1068359", "1251725", "1832174"})
COLUMNS = (
    "question_id", "question_text", "forecasted_at", "source_cutoff_at",
    "event_id", "category",
)


class AuditError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm(value: object) -> str:
    text = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n")
    return " ".join(text.replace("\r", "\n").split()).strip()


def canon_hash(value: object) -> str:
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode())


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"Expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise AuditError(f"Expected JSONL object: {path}")
            rows.append(value)
    return rows


def utc(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def load_candidates(path: Path) -> pd.DataFrame:
    if sha(path.read_bytes()) != CANDIDATE_SHA:
        raise AuditError("Candidate CSV digest changed")
    frame = pd.read_csv(path, dtype={"question_id": str})
    if len(frame) != 64 or tuple(frame.columns) != COLUMNS:
        raise AuditError("Candidate artifact shape changed")
    if frame.question_id.nunique() != 64:
        raise AuditError("Candidate IDs changed")
    return frame


def load_labels(path: Path, candidates: pd.DataFrame) -> dict[str, int]:
    if sha(path.read_bytes()) != DEVELOPMENT_SHA:
        raise AuditError("Development CSV digest changed")
    dev = pd.read_csv(path, dtype={"question_id": str},
                      usecols=["question_id", "question_text", "outcome", "split"])
    if not (dev.split == "development").all():
        raise AuditError("Non-development row in custody derivative")
    dev = dev.set_index("question_id", drop=False)
    result = {}
    for row in candidates.itertuples(index=False):
        qid = str(row.question_id)
        if qid not in dev.index or isinstance(dev.loc[qid], pd.DataFrame):
            raise AuditError(f"Missing/duplicate development row: {qid}")
        source = dev.loc[qid]
        if norm(source.question_text) != norm(row.question_text):
            raise AuditError(f"Question text changed: {qid}")
        outcome = source.outcome
        if float(outcome) not in {0.0, 1.0}:
            raise AuditError(f"Non-binary outcome: {qid}")
        result[qid] = int(outcome)
    return result


def load_sources(root: Path) -> list[dict[str, Any]]:
    summary = read_json(root / "source-discovery-v2-summary.json")
    expected = {
        "candidate_rows": 64,
        "candidate_sha256": CANDIDATE_SHA,
        "code_commit": SOURCE_CODE,
        "lookup_rows": 384,
        "questions_with_capture": 3,
        "exact_question_match_diagnostics": 3,
    }
    if any(summary.get(k) != v for k, v in expected.items()):
        raise AuditError("Canonical source-discovery identity changed")
    rows = read_jsonl(root / "source-lookups-v2.jsonl")
    if len(rows) != 384:
        raise AuditError("Canonical source lookup count changed")
    return rows


def contract_check(
    candidate: pd.Series, rows: list[dict[str, Any]], root: Path
) -> dict[str, Any]:
    qid = str(candidate.question_id)
    relevant = [r for r in rows if str(r.get("question_id")) == qid]
    if not relevant:
        raise AuditError(f"Source discovery omitted candidate: {qid}")
    captures = [r for r in relevant if r.get("lookup_status") == "capture"]
    if not captures:
        return {
            "status": "unknown",
            "reason_codes": ["precutoff_contract_capture_missing"],
            "evidence": [],
        }
    evidence, exact, mismatch = [], False, False
    for row in captures:
        capture, content = row.get("capture"), row.get("content")
        if not isinstance(capture, dict) or not isinstance(content, dict):
            raise AuditError(f"Malformed capture: {qid}")
        captured_at = utc(capture.get("timestamp"))
        if captured_at > utc(candidate.forecasted_at):
            raise AuditError(f"Post-forecast capture: {qid}")
        match = content.get("benchmark_question_exact_match")
        exact |= match is True
        mismatch |= match is False
        text_sha = content.get("text_sha256")
        provider = str(row.get("provider") or "")
        text_path = root / "text" / f"{provider}-{text_sha}.txt"
        if not isinstance(text_sha, str) or not text_path.is_file():
            raise AuditError(f"Frozen capture text missing: {qid}")
        if sha(text_path.read_bytes()) != text_sha:
            raise AuditError(f"Frozen capture text changed: {qid}")
        evidence.append({
            "provider": provider,
            "pattern": row.get("pattern"),
            "requested_url": row.get("url"),
            "capture_timestamp": captured_at.isoformat(),
            "captured_url": capture.get("captured_url"),
            "replay_reference": capture.get("replay_reference"),
            "raw_sha256": content.get("raw_sha256"),
            "historical_text_sha256": text_sha,
            "benchmark_question_exact_match": match is True,
        })
    if mismatch:
        return {
            "status": "contradicted",
            "reason_codes": ["precutoff_contract_mismatch"],
            "evidence": evidence,
        }
    if exact:
        return {"status": "verified",
                "reason_codes": ["precutoff_contract_capture_exact_match"],
                "evidence": evidence}
    return {"status": "unknown", "reason_codes": ["precutoff_contract_capture_missing"],
            "evidence": evidence}


def load_evidence(path: Path) -> dict[str, dict[str, Any]]:
    value = read_json(path)
    if value.get("protocol_commit") != PROTOCOL_COMMIT:
        raise AuditError("Evidence protocol binding changed")
    if value.get("candidate_sha256") != CANDIDATE_SHA:
        raise AuditError("Evidence candidate binding changed")
    if value.get("source_discovery_artifact_id") != SOURCE_ID:
        raise AuditError("Evidence source artifact ID changed")
    if value.get("source_discovery_artifact_digest") != SOURCE_DIGEST:
        raise AuditError("Evidence source artifact digest changed")
    cases = value.get("cases")
    if not isinstance(cases, dict) or set(cases) != A_VERIFIED:
        raise AuditError("Evidence must cover exactly the three A-verified cases")
    return cases


def outcome_name(value: int) -> str:
    return "Yes" if value == 1 else "No"


def adjudicate_b(forecasted_at: object, evidence: dict[str, Any]) -> dict[str, Any]:
    declared = evidence.get("status")
    if declared == "unknown":
        status, reason, event_at = "unknown", "decisive_fact_timestamp_unresolved", None
    else:
        raw = evidence.get("decisive_event_at") or evidence.get(
            "decisive_event_lower_bound_utc"
        )
        if declared not in {"verified", "contradicted"} or not raw:
            raise AuditError("Malformed B evidence")
        event = utc(raw)
        status = "verified" if event > utc(forecasted_at) else "contradicted"
        if status != declared:
            raise AuditError("B declaration disagrees with event/forecast ordering")
        reason = ("decisive_fact_after_forecast" if status == "verified"
                  else "decisive_fact_at_or_before_forecast")
        event_at = event.isoformat()
    return {"status": status, "reason_codes": [reason],
            "decisive_event_at_or_lower_bound": event_at,
            "timestamp_precision": evidence.get("timestamp_precision"),
            "evidence_note_sha256": canon_hash(evidence),
            "sources": evidence.get("sources", [])}


def adjudicate_c(label: int, evidence: dict[str, Any]) -> dict[str, Any]:
    authoritative = evidence.get("authoritative_outcome")
    if authoritative is None:
        status, reason = "unknown", "authoritative_label_unresolved"
    elif authoritative in {"Yes", "No"}:
        status = "verified" if authoritative == outcome_name(label) else "contradicted"
        reason = ("authoritative_label_matches" if status == "verified"
                  else "authoritative_label_disagrees")
    else:
        raise AuditError("Authoritative outcome must be Yes/No")
    if evidence.get("status") != status:
        raise AuditError("C declaration disagrees with canonical label comparison")
    return {"status": status, "reason_codes": [reason],
            "authoritative_outcome": authoritative,
            "canonical_outcome": outcome_name(label),
            "evidence_note_sha256": canon_hash(evidence),
            "sources": evidence.get("sources", [])}


def unknown_bc(label: int) -> tuple[dict[str, Any], dict[str, Any]]:
    reason = ["historical_contract_terms_unavailable"]
    return (
        {"status": "unknown", "reason_codes": reason,
         "decisive_event_at_or_lower_bound": None, "timestamp_precision": None,
         "evidence_note_sha256": None, "sources": []},
        {"status": "unknown", "reason_codes": reason,
         "authoritative_outcome": None, "canonical_outcome": outcome_name(label),
         "evidence_note_sha256": None, "sources": []},
    )


def overall(a: str, b: str, c: str) -> str:
    if "contradicted" in {a, b, c}:
        return "invalid"
    return "verified_valid" if {a, b, c} == {"verified"} else "unknown"


def build_audit(
    candidates_csv: Path,
    development_csv: Path,
    source_root: Path,
    evidence_json: Path,
    output_dir: Path,
    code_commit: str,
) -> dict[str, Any]:
    if output_dir.exists():
        raise AuditError("Refusing to replace audit output")
    candidates = load_candidates(candidates_csv)
    labels = load_labels(development_csv, candidates)
    sources = load_sources(source_root)
    manual = load_evidence(evidence_json)
    a_checks = {str(r.question_id): contract_check(r, sources, source_root)
                for _, r in candidates.iterrows()}
    verified = {qid for qid, check in a_checks.items() if check["status"] == "verified"}
    if verified != A_VERIFIED:
        raise AuditError("A-verified set changed")

    rows = []
    for _, candidate in candidates.iterrows():
        qid = str(candidate.question_id)
        a, label = a_checks[qid], labels[qid]
        if a["status"] == "verified":
            item = manual[qid]
            if norm(item.get("question")) != norm(candidate.question_text):
                raise AuditError(f"Evidence question mismatch: {qid}")
            b = adjudicate_b(candidate.forecasted_at, item["b"])
            c = adjudicate_c(label, item["c"])
        else:
            b, c = unknown_bc(label)
        rows.append({
            "question_id": qid, "event_id": candidate.event_id,
            "question_text": candidate.question_text,
            "normalized_frozen_question_sha256": sha(
                norm(candidate.question_text).encode()
            ),
            "forecasted_at": candidate.forecasted_at,
            "source_cutoff_at": candidate.source_cutoff_at,
            "canonical_outcome": outcome_name(label),
            "a_contract_identity": a, "b_outcome_unknowability": b,
            "c_authoritative_final_label": c,
            "overall_classification": overall(a["status"], b["status"], c["status"]),
            "retrospective_close_anchored_schedule": True,
            "candidate_sha256": CANDIDATE_SHA,
            "source_discovery_artifact_id": SOURCE_ID,
            "source_discovery_artifact_digest": SOURCE_DIGEST,
            "adjudication_protocol_commit": PROTOCOL_COMMIT,
            "adjudication_evidence_commit": EVIDENCE_COMMIT,
            "code_commit": code_commit,
        })
    counts = Counter(r["overall_classification"] for r in rows)
    if (counts["verified_valid"], counts["invalid"], counts["unknown"]) != (3, 0, 61):
        raise AuditError("Audit classification counts changed")

    output_dir.mkdir(parents=True)
    (output_dir / "historical-validity-audit-v1.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8")
    shutil.copyfile(
        evidence_json,
        output_dir / "historical-validity-adjudication-v1-evidence.json",
    )
    def count(field: str) -> dict[str, int]:
        return dict(sorted(Counter(r[field]["status"] for r in rows).items()))
    summary = {
        "schema_version": 1, "purpose": "development-historical-validity-audit-v1",
        "candidate_rows": 64, "candidate_sha256": CANDIDATE_SHA,
        "development_sha256": DEVELOPMENT_SHA,
        "source_discovery_artifact_id": SOURCE_ID,
        "source_discovery_artifact_digest": SOURCE_DIGEST,
        "source_discovery_code_commit": SOURCE_CODE,
        "adjudication_protocol_commit": PROTOCOL_COMMIT,
        "adjudication_evidence_commit": EVIDENCE_COMMIT, "code_commit": code_commit,
        "a_status_counts": count("a_contract_identity"),
        "b_status_counts": count("b_outcome_unknowability"),
        "c_status_counts": count("c_authoritative_final_label"),
        "overall_classification_counts": {
            k: counts[k] for k in ("verified_valid", "invalid", "unknown")
        },
        "verified_valid_question_ids": [
            r["question_id"]
            for r in rows
            if r["overall_classification"] == "verified_valid"
        ],
        "retrospective_close_anchored_schedule": True,
        "forecaster_run": False, "reserved_holdout_accessed": False,
    }
    (output_dir / "historical-validity-audit-v1-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("candidates_csv", type=Path)
    p.add_argument("development_csv", type=Path)
    p.add_argument("source_root", type=Path)
    p.add_argument("evidence_json", type=Path)
    p.add_argument("output_dir", type=Path)
    p.add_argument("--code-commit", required=True)
    a = p.parse_args()
    print(json.dumps(build_audit(a.candidates_csv, a.development_csv, a.source_root,
                                 a.evidence_json, a.output_dir, a.code_commit),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
