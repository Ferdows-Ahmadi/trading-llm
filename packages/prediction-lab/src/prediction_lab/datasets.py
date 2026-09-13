from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from prediction_lab.cases import normalize_case_frame

_TIMESTAMP_COLUMNS = (
    "forecasted_at",
    "resolved_at",
    "market_price_timestamp",
    "source_cutoff_at",
)


class DatasetFreezeError(ValueError):
    """Raised when a benchmark dataset cannot be frozen or verified safely."""


@dataclass(frozen=True)
class DatasetManifest:
    schema_version: int
    source_name: str
    source_revision: str
    selection_policy: str
    row_count: int
    question_count: int
    forecast_start: str
    forecast_end: str
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def require_one_case_per_question(cases: pd.DataFrame) -> pd.DataFrame:
    """Require one benchmark observation per resolved question."""

    if "question_id" in cases.columns:
        raw_ids = cases["question_id"].astype(str)
        duplicated = raw_ids.duplicated(keep=False)
        if duplicated.any():
            question_ids = sorted(raw_ids.loc[duplicated].unique().tolist())[:5]
            raise DatasetFreezeError(
                "Benchmark cases must contain one observation per question; duplicates include "
                f"{question_ids}"
            )

    normalized = normalize_case_frame(cases)
    return normalized


def _utc_cutoff(value: str | pd.Timestamp) -> pd.Timestamp:
    cutoff = pd.Timestamp(value)
    if cutoff.tzinfo is None:
        return cutoff.tz_localize("UTC")
    return cutoff.tz_convert("UTC")


def temporal_question_split(
    cases: pd.DataFrame,
    *,
    holdout_start: str | pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split single-observation questions into development and temporal holdout sets."""

    normalized = require_one_case_per_question(cases)
    cutoff = _utc_cutoff(holdout_start)

    development = normalized.loc[normalized["forecasted_at"] < cutoff].copy()
    holdout = normalized.loc[normalized["forecasted_at"] >= cutoff].copy()

    if development.empty or holdout.empty:
        raise DatasetFreezeError(
            "Temporal split must produce non-empty development and holdout sets"
        )
    if development["forecasted_at"].max() >= holdout["forecasted_at"].min():
        raise DatasetFreezeError("Temporal split overlap detected")

    development["split"] = "development"
    holdout["split"] = "holdout"
    return development.reset_index(drop=True), holdout.reset_index(drop=True)


def purged_temporal_group_split(
    cases: pd.DataFrame,
    *,
    holdout_start: str | pd.Timestamp,
    group_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-split cases and purge holdout groups previously seen in development.

    Prediction markets frequently contain several mutually related questions under one
    parent event. A plain question-level temporal split can therefore place sibling
    markets in both development and holdout. This helper retains development data and
    removes every holdout row whose group was already observed before the cutoff.
    """

    normalized = require_one_case_per_question(cases)
    if group_column not in normalized.columns:
        raise DatasetFreezeError(f"Missing group column for purged split: {group_column}")

    raw_groups = normalized[group_column]
    if raw_groups.isna().any() or raw_groups.astype(str).str.strip().eq("").any():
        raise DatasetFreezeError(f"Group column {group_column} must not contain null/blank values")

    cutoff = _utc_cutoff(holdout_start)
    development = normalized.loc[normalized["forecasted_at"] < cutoff].copy()
    holdout = normalized.loc[normalized["forecasted_at"] >= cutoff].copy()
    if development.empty or holdout.empty:
        raise DatasetFreezeError(
            "Temporal split must produce non-empty development and holdout sets before purging"
        )

    development_groups = set(development[group_column].astype(str))
    holdout_groups = holdout[group_column].astype(str)
    holdout = holdout.loc[~holdout_groups.isin(development_groups)].copy()
    if holdout.empty:
        raise DatasetFreezeError("Group purging removed the entire temporal holdout")

    remaining_overlap = development_groups & set(holdout[group_column].astype(str))
    if remaining_overlap:
        raise DatasetFreezeError("Group overlap remains after purging")
    if development["forecasted_at"].max() >= holdout["forecasted_at"].min():
        raise DatasetFreezeError("Temporal split overlap detected after group purging")

    development["split"] = "development"
    holdout["split"] = "holdout"
    return development.reset_index(drop=True), holdout.reset_index(drop=True)


def _stable_csv_bytes(cases: pd.DataFrame) -> bytes:
    normalized = require_one_case_per_question(cases).copy()
    normalized.sort_values(["forecasted_at", "question_id"], inplace=True)

    for column in _TIMESTAMP_COLUMNS:
        normalized[column] = normalized[column].dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    csv_text = normalized.to_csv(index=False, lineterminator="\n")
    return csv_text.encode("utf-8")


def freeze_cases(
    cases: pd.DataFrame,
    *,
    csv_path: str | Path,
    manifest_path: str | Path,
    source_name: str,
    source_revision: str,
    selection_policy: str,
) -> DatasetManifest:
    """Write a deterministic benchmark CSV plus a content-hash manifest."""

    if not source_name.strip() or not source_revision.strip() or not selection_policy.strip():
        raise DatasetFreezeError(
            "source_name, source_revision, and selection_policy must be non-empty"
        )

    normalized = require_one_case_per_question(cases)
    if normalized.empty:
        raise DatasetFreezeError("Cannot freeze an empty dataset")

    payload = _stable_csv_bytes(normalized)
    digest = hashlib.sha256(payload).hexdigest()

    csv_file = Path(csv_path)
    manifest_file = Path(manifest_path)
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    csv_file.write_bytes(payload)

    manifest = DatasetManifest(
        schema_version=1,
        source_name=source_name.strip(),
        source_revision=source_revision.strip(),
        selection_policy=selection_policy.strip(),
        row_count=len(normalized),
        question_count=normalized["question_id"].nunique(),
        forecast_start=normalized["forecasted_at"].min().isoformat(),
        forecast_end=normalized["forecasted_at"].max().isoformat(),
        sha256=digest,
    )
    manifest_file.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def verify_frozen_dataset(
    *,
    csv_path: str | Path,
    manifest_path: str | Path,
) -> pd.DataFrame:
    """Verify content hash and manifest counts before loading benchmark cases."""

    csv_file = Path(csv_path)
    manifest_file = Path(manifest_path)
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    expected_hash = str(manifest_data["sha256"])
    payload = csv_file.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != expected_hash:
        raise DatasetFreezeError(
            f"Dataset hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    frame = pd.read_csv(csv_file)
    normalized = require_one_case_per_question(frame)
    if len(normalized) != int(manifest_data["row_count"]):
        raise DatasetFreezeError("Dataset row count does not match manifest")
    if normalized["question_id"].nunique() != int(manifest_data["question_count"]):
        raise DatasetFreezeError("Dataset question count does not match manifest")
    return normalized
