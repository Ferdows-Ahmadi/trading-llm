"""Freeze fresh development-only candidates for the historical-validity audit.

This module implements the deterministic selection preregistered in
``docs/experiments/development-historical-validity-v1-preregistration.md``.
It never consumes outcomes, market probabilities, resolution timestamps, or model results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from prediction_lab.research_types import ResearchContractError

PREREGISTRATION_COMMIT = "c3a66d28d7126155935ccdd255034e7560dce6f0"
SOURCE_DEVELOPMENT_SHA256 = "c05cbfa404804789faec779877c839b6655abc317217f182a673b2e91bd9f9a7"
SOURCE_DEVELOPMENT_ROWS = 255
SOURCE_DEVELOPMENT_EVENT_GROUPS = 84

PILOT_EVENT_IDS = frozenset(
    {
        "polymarket-event:57370",
        "polymarket-event:96761",
        "polymarket-event:84910",
        "polymarket-event:84066",
        "polymarket-event:131190",
        "polymarket-event:147521",
        "polymarket-event:159929",
        "polymarket-event:161872",
        "polymarket-event:89583",
        "polymarket-event:189755",
        "polymarket-event:89519",
        "polymarket-event:153927",
        "polymarket-event:192882",
        "polymarket-event:217185",
        "polymarket-event:127101",
        "polymarket-event:133755",
        "polymarket-event:181347",
        "polymarket-event:73835",
        "polymarket-event:230200",
        "polymarket-event:84921",
    }
)

CANDIDATE_COLUMNS = (
    "question_id",
    "question_text",
    "forecasted_at",
    "source_cutoff_at",
    "event_id",
    "category",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchContractError(f"Cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchContractError(f"Expected JSON object in {path}")
    return value


def build_fresh_candidates(
    *,
    development_csv: Path,
    development_manifest: Path,
) -> pd.DataFrame:
    """Derive one fresh representative per non-pilot development parent event."""

    payload = development_csv.read_bytes()
    actual_sha = _sha256_bytes(payload)
    if actual_sha != SOURCE_DEVELOPMENT_SHA256:
        raise ResearchContractError(
            f"Canonical development CSV digest mismatch: {actual_sha}"
        )

    manifest = _load_json(development_manifest)
    if manifest.get("sha256") != SOURCE_DEVELOPMENT_SHA256:
        raise ResearchContractError("Development manifest does not bind the canonical CSV")
    if manifest.get("row_count") != SOURCE_DEVELOPMENT_ROWS:
        raise ResearchContractError("Development manifest row count changed")

    required = [*CANDIDATE_COLUMNS, "split"]
    try:
        frame = pd.read_csv(development_csv, usecols=required)
    except (OSError, ValueError) as exc:
        raise ResearchContractError(f"Cannot load authorized development columns: {exc}") from exc

    if len(frame) != SOURCE_DEVELOPMENT_ROWS:
        raise ResearchContractError("Canonical development row count changed")
    if set(frame["split"].astype(str)) != {"development"}:
        raise ResearchContractError("Candidate source contains a non-development row")
    if frame["event_id"].isna().any() or frame["event_id"].astype(str).str.strip().eq("").any():
        raise ResearchContractError("Candidate source contains a blank event_id")
    if frame["event_id"].astype(str).nunique() != SOURCE_DEVELOPMENT_EVENT_GROUPS:
        raise ResearchContractError("Canonical development event-group count changed")

    available_events = set(frame["event_id"].astype(str))
    missing_pilot_events = sorted(PILOT_EVENT_IDS - available_events)
    if missing_pilot_events:
        raise ResearchContractError(
            f"Frozen pilot event exclusions are absent from development: {missing_pilot_events}"
        )

    safe = frame.loc[
        ~frame["event_id"].astype(str).isin(PILOT_EVENT_IDS), list(CANDIDATE_COLUMNS)
    ].copy()
    safe["question_id"] = safe["question_id"].astype(str)
    safe["event_id"] = safe["event_id"].astype(str)
    safe["question_text"] = safe["question_text"].astype(str)
    safe["forecasted_at"] = pd.to_datetime(safe["forecasted_at"], utc=True, errors="raise")
    safe["source_cutoff_at"] = pd.to_datetime(
        safe["source_cutoff_at"], utc=True, errors="raise"
    )
    safe.sort_values(["forecasted_at", "question_id"], inplace=True)
    candidates = safe.drop_duplicates("event_id", keep="first").reset_index(drop=True)

    if candidates.empty:
        raise ResearchContractError("Fresh candidate derivation produced no rows")
    if candidates["event_id"].nunique() != len(candidates):
        raise ResearchContractError("Fresh candidate cohort is not event-independent")
    if set(candidates["event_id"]) & PILOT_EVENT_IDS:
        raise ResearchContractError("Fresh candidate cohort contains a repeatedly inspected pilot event")
    return candidates


def _stable_candidate_csv(candidates: pd.DataFrame) -> bytes:
    stable = candidates.loc[:, list(CANDIDATE_COLUMNS)].copy()
    for column in ("forecasted_at", "source_cutoff_at"):
        stable[column] = pd.to_datetime(stable[column], utc=True, errors="raise").dt.strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
    return stable.to_csv(index=False, lineterminator="\n").encode("utf-8")


def freeze_fresh_candidates(
    *,
    development_csv: Path,
    development_manifest: Path,
    output_csv: Path,
    output_manifest: Path,
    code_commit: str,
    source_artifact_id: int,
    source_artifact_digest: str,
) -> dict[str, object]:
    candidates = build_fresh_candidates(
        development_csv=development_csv,
        development_manifest=development_manifest,
    )
    payload = _stable_candidate_csv(candidates)
    digest = _sha256_bytes(payload)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_csv.write_bytes(payload)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "purpose": "development-historical-validity-v1-candidates",
        "row_count": len(candidates),
        "event_group_count": candidates["event_id"].nunique(),
        "forecast_start": pd.to_datetime(candidates["forecasted_at"], utc=True).min().isoformat(),
        "forecast_end": pd.to_datetime(candidates["forecasted_at"], utc=True).max().isoformat(),
        "sha256": digest,
        "source_development_sha256": SOURCE_DEVELOPMENT_SHA256,
        "source_artifact_id": source_artifact_id,
        "source_artifact_digest": source_artifact_digest,
        "pilot_exclusion_event_count": len(PILOT_EVENT_IDS),
        "pilot_exclusion_event_ids_sha256": _sha256_bytes(
            ("\n".join(sorted(PILOT_EVENT_IDS)) + "\n").encode("utf-8")
        ),
        "selection_policy": (
            "Verified canonical development only; exclude preregistered pilot parent events; "
            "sort forecasted_at/question_id; retain first row per remaining event_id; retain all."
        ),
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "code_commit": code_commit,
        "retrospective_close_anchored_schedule": True,
        "columns": list(CANDIDATE_COLUMNS),
    }
    output_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze preregistered fresh validity candidates")
    parser.add_argument("development_csv", type=Path)
    parser.add_argument("development_manifest", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("output_manifest", type=Path)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--source-artifact-id", required=True, type=int)
    parser.add_argument("--source-artifact-digest", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    manifest = freeze_fresh_candidates(
        development_csv=args.development_csv,
        development_manifest=args.development_manifest,
        output_csv=args.output_csv,
        output_manifest=args.output_manifest,
        code_commit=args.code_commit,
        source_artifact_id=args.source_artifact_id,
        source_artifact_digest=args.source_artifact_digest,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
