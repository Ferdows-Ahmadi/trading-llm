from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prediction_lab.datasets import (
    DatasetFreezeError,
    DatasetManifest,
    freeze_cases,
    verify_frozen_dataset,
)


def _discovery_question_ids(path: str | Path) -> tuple[str, ...]:
    question_ids: list[str] = []
    seen: set[str] = set()
    source = Path(path)
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetFreezeError(
                f"Malformed discovery JSONL at line {line_number}"
            ) from exc
        if not isinstance(record, dict):
            raise DatasetFreezeError(
                f"Discovery JSONL line {line_number} must be an object"
            )
        question_id = str(record.get("question_id") or "").strip()
        if not question_id:
            raise DatasetFreezeError(
                f"Discovery JSONL line {line_number} has no question_id"
            )
        if question_id in seen:
            raise DatasetFreezeError(f"Duplicate pilot question_id: {question_id}")
        seen.add(question_id)
        question_ids.append(question_id)
    if not question_ids:
        raise DatasetFreezeError("Discovery JSONL contains no pilot question IDs")
    return tuple(question_ids)


def build_development_pilot(
    *,
    development_csv: str | Path,
    development_manifest: str | Path,
    discovery_jsonl: str | Path,
    output_csv: str | Path,
    output_manifest: str | Path,
    expected_question_count: int | None = None,
) -> DatasetManifest:
    """Freeze exactly the development rows named by a frozen discovery artifact."""
    development = verify_frozen_dataset(
        csv_path=development_csv,
        manifest_path=development_manifest,
    )
    if set(development["split"].astype(str)) != {"development"}:
        raise DatasetFreezeError("Pilot builder accepts development rows only")

    question_ids = _discovery_question_ids(discovery_jsonl)
    if expected_question_count is not None and len(question_ids) != expected_question_count:
        raise DatasetFreezeError(
            f"Expected {expected_question_count} pilot questions, found {len(question_ids)}"
        )

    available = set(development["question_id"].astype(str))
    missing = sorted(set(question_ids) - available)
    if missing:
        raise DatasetFreezeError(f"Pilot IDs missing from development benchmark: {missing[:5]}")

    pilot = development.loc[
        development["question_id"].astype(str).isin(question_ids)
    ].copy()
    if len(pilot) != len(question_ids):
        raise DatasetFreezeError("Pilot row count does not match frozen discovery question IDs")

    parent_manifest_bytes = Path(development_manifest).read_bytes()
    discovery_bytes = Path(discovery_jsonl).read_bytes()
    revision_hash = hashlib.sha256(parent_manifest_bytes + b"\0" + discovery_bytes).hexdigest()
    selection_policy = (
        "Exact question_id intersection of the verified frozen development benchmark "
        "with the frozen GDELT discovery pilot; no outcome-based selection."
    )
    return freeze_cases(
        pilot,
        csv_path=output_csv,
        manifest_path=output_manifest,
        source_name="polymarket-public-v0.1-clean-development-pilot",
        source_revision=f"sha256:{revision_hash}",
        selection_policy=selection_policy,
    )
