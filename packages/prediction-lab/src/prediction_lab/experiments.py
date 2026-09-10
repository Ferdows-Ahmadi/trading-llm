from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from prediction_lab.benchmark import choose_temporal_holdout_start
from prediction_lab.cases import attach_model_probabilities
from prediction_lab.datasets import purged_temporal_group_split, verify_frozen_dataset
from prediction_lab.evaluation import evaluate_forecasts
from prediction_lab.evidence import EvidenceProvider
from prediction_lab.research_cache import FilesystemForecastCache, write_immutable_json
from prediction_lab.research_forecaster import StructuredModelAdapter, forecast_question
from prediction_lab.research_types import (
    ForecastArtifact,
    ForecastMode,
    ResearchContractError,
    content_hash,
    format_utc,
)


@dataclass(frozen=True)
class ExperimentConfig:
    schema_version: int
    experiment_id: str
    hypothesis: str
    benchmark_hash: str
    dataset_role: str
    prompt_version: str
    mode: ForecastMode
    validation_fraction: float | None
    parent_group_column: str
    research_cutoff_policy: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def config_hash(self) -> str:
        return content_hash(self.to_dict())


def _require_text(value: str, *, field: str) -> str:
    if not value.strip():
        raise ResearchContractError(f"{field} cannot be empty")
    return value.strip()


def _git_commit(repository_root: Path | None) -> str:
    if repository_root is None:
        return "unavailable"
    git_executable = shutil.which("git")
    if git_executable is None:
        return "unavailable"
    try:
        commit = subprocess.run(  # noqa: S603 - resolved executable and fixed arguments
            [git_executable, "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(  # noqa: S603 - resolved executable and fixed arguments
                [git_executable, "status", "--porcelain"],
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return f"{commit}+dirty" if dirty else commit


def _load_manifest(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchContractError(f"Cannot read dataset manifest {path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("sha256"), str):
        raise ResearchContractError("Dataset manifest must contain a sha256 string")
    return value


def inner_development_validation_split(
    cases: pd.DataFrame,
    *,
    validation_fraction: float,
    parent_group_column: str = "event_id",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Create a temporal inner split and purge parent groups from validation."""

    if not 0.05 <= validation_fraction <= 0.5:
        raise ResearchContractError("validation_fraction must be between 0.05 and 0.5")
    cutoff = choose_temporal_holdout_start(cases, holdout_fraction=validation_fraction)
    development, validation = purged_temporal_group_split(
        cases,
        holdout_start=cutoff,
        group_column=parent_group_column,
    )
    overlap = set(development[parent_group_column].astype(str)) & set(
        validation[parent_group_column].astype(str)
    )
    if overlap:
        raise ResearchContractError("Parent-event groups cross the inner split")
    return development, validation, cutoff


def _select_evaluation_cases(
    cases: pd.DataFrame,
    *,
    validation_fraction: float | None,
    parent_group_column: str,
) -> tuple[pd.DataFrame, dict[str, object] | None]:
    if validation_fraction is None:
        return cases.sort_values(["forecasted_at", "question_id"]).reset_index(drop=True), None
    development, validation, cutoff = inner_development_validation_split(
        cases,
        validation_fraction=validation_fraction,
        parent_group_column=parent_group_column,
    )
    return validation, {
        "cutoff": format_utc(cutoff.to_pydatetime()),
        "development_parent_groups": development[parent_group_column].nunique(),
        "development_rows": len(development),
        "parent_group_column": parent_group_column,
        "purged_rows": len(cases) - len(development) - len(validation),
        "validation_parent_groups": validation[parent_group_column].nunique(),
        "validation_rows": len(validation),
    }


def _failure_payload(
    *, question_id: str, forecasted_at: pd.Timestamp, error: Exception
) -> dict[str, object]:
    return {
        "error_message": str(error),
        "error_type": type(error).__name__,
        "forecasted_at": format_utc(forecasted_at.to_pydatetime()),
        "question_id": question_id,
    }


def run_development_experiment(
    *,
    development_csv: str | Path,
    development_manifest: str | Path,
    evidence_provider: EvidenceProvider,
    adapter: StructuredModelAdapter,
    output_directory: str | Path,
    experiment_id: str,
    hypothesis: str,
    prompt_version: str,
    mode: ForecastMode,
    validation_fraction: float | None = None,
    parent_group_column: str = "event_id",
    repository_root: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Run a resumable, network-free experiment against development data only."""

    if mode not in {"blind", "market-aware"}:
        raise ResearchContractError("mode must be blind or market-aware")
    csv_path = Path(development_csv)
    manifest_path = Path(development_manifest)
    cases = verify_frozen_dataset(csv_path=csv_path, manifest_path=manifest_path)
    manifest = _load_manifest(manifest_path)
    benchmark_hash = str(manifest["sha256"])
    split_values = set(cases["split"].astype(str))
    if split_values != {"development"}:
        raise ResearchContractError(
            "Development runner accepts only datasets whose split is explicitly development"
        )
    if parent_group_column not in cases.columns:
        raise ResearchContractError(
            f"Development dataset lacks parent group column {parent_group_column}"
        )
    raw_parent_groups = cases[parent_group_column]
    if raw_parent_groups.isna().any() or raw_parent_groups.astype(str).str.strip().eq("").any():
        raise ResearchContractError(
            f"Parent group column {parent_group_column} contains null or blank values"
        )
    config = ExperimentConfig(
        schema_version=1,
        experiment_id=_require_text(experiment_id, field="experiment_id"),
        hypothesis=_require_text(hypothesis, field="hypothesis"),
        benchmark_hash=benchmark_hash,
        dataset_role="development-only",
        prompt_version=_require_text(prompt_version, field="prompt_version"),
        mode=mode,
        validation_fraction=validation_fraction,
        parent_group_column=_require_text(parent_group_column, field="parent_group_column"),
        research_cutoff_policy="source_cutoff_at; every evidence available_at must be <= cutoff",
    )
    evaluation_cases, split_summary = _select_evaluation_cases(
        cases,
        validation_fraction=validation_fraction,
        parent_group_column=config.parent_group_column,
    )
    if evaluation_cases.empty:
        raise ResearchContractError("Experiment selection produced no evaluation cases")

    earliest_forecast = evaluation_cases["forecasted_at"].min()
    adapter.metadata.assert_safe_for_historical_scoring(earliest_forecast.to_pydatetime())

    output_root = Path(output_directory)
    cache = FilesystemForecastCache(output_root / "cache")
    code_commit = _git_commit(
        Path(repository_root) if repository_root is not None else Path.cwd()
    )

    successes: list[tuple[pd.Series, ForecastArtifact]] = []
    failures: list[dict[str, object]] = []
    artifact_records: list[dict[str, str]] = []
    evidence_records: list[dict[str, str]] = []
    ordered = evaluation_cases.sort_values(["forecasted_at", "question_id"])
    for _, row in ordered.iterrows():
        question_id = str(row["question_id"])
        try:
            packet = evidence_provider.build_packet(
                question_id=question_id,
                forecasted_at=row["forecasted_at"].to_pydatetime(),
                research_cutoff_at=row["source_cutoff_at"].to_pydatetime(),
            )
            if packet.forecasted_at != row["forecasted_at"].to_pydatetime():
                raise ResearchContractError(
                    f"Evidence provider changed forecasted_at for {question_id}"
                )
            if packet.research_cutoff_at != row["source_cutoff_at"].to_pydatetime():
                raise ResearchContractError(
                    f"Evidence provider changed research cutoff for {question_id}"
                )
            write_immutable_json(
                output_root / "evidence" / f"{packet.packet_hash}.json",
                packet.to_dict(),
            )
            evidence_records.append(
                {"packet_hash": packet.packet_hash, "question_id": question_id}
            )
            artifact, _cache_hit = forecast_question(
                experiment_id=config.experiment_id,
                benchmark_hash=config.benchmark_hash,
                code_commit=code_commit,
                experiment_config_hash=config.config_hash,
                question_id=question_id,
                question_text=str(row["question_text"]),
                evidence_packet=packet,
                prompt_version=config.prompt_version,
                mode=config.mode,
                market_probability=(
                    float(row["market_probability"]) if config.mode == "market-aware" else None
                ),
                adapter=adapter,
                cache=cache,
            )
            write_immutable_json(
                output_root / "artifacts" / f"{artifact.artifact_hash}.json",
                artifact.to_dict(),
            )
            successes.append((row, artifact))
            artifact_records.append(
                {"artifact_hash": artifact.artifact_hash, "question_id": question_id}
            )
        except Exception as exc:
            failure = _failure_payload(
                question_id=question_id,
                forecasted_at=row["forecasted_at"],
                error=exc,
            )
            failures.append(failure)
            failure_hash = content_hash(failure)
            write_immutable_json(output_root / "failures" / f"{failure_hash}.json", failure)

    evaluation: dict[str, Any] | None = None
    if successes:
        successful_cases = pd.DataFrame([row.to_dict() for row, _ in successes])
        probabilities = [artifact.final_probability for _, artifact in successes]
        evaluation_frame = attach_model_probabilities(
            successful_cases,
            probabilities,
            model_name=(
                f"{adapter.metadata.provider}/{adapter.metadata.model_id}:"
                f"{adapter.metadata.immutable_version}:{config.mode}"
            ),
        )
        evaluation = evaluate_forecasts(evaluation_frame).to_dict()

    total = len(evaluation_cases)
    succeeded = len(successes)
    forecast_start = evaluation_cases["forecasted_at"].min()
    forecast_end = evaluation_cases["forecasted_at"].max()
    market_staleness_hours = (
        evaluation_cases["forecasted_at"] - evaluation_cases["market_price_timestamp"]
    ).dt.total_seconds() / 3600.0
    horizon_days = (
        evaluation_cases["resolved_at"] - evaluation_cases["forecasted_at"]
    ).dt.total_seconds() / 86400.0
    run_identity_hash = content_hash(
        {
            "code_commit": code_commit,
            "evidence_packets": evidence_records,
            "evidence_provider": type(evidence_provider).__name__,
            "experiment_config_hash": config.config_hash,
            "model_metadata": adapter.metadata.to_dict(),
        }
    )
    summary: dict[str, Any] = {
        "artifact_records": artifact_records,
        "benchmark_hash": benchmark_hash,
        "code_commit": code_commit,
        "config": config.to_dict(),
        "experiment_config_hash": config.config_hash,
        "run_identity_hash": run_identity_hash,
        "evaluation": evaluation,
        "execution": {
            "failed_forecasts": len(failures),
            "forecast_coverage": succeeded / total if total else 0.0,
            "successful_forecasts": succeeded,
            "total_questions": total,
        },
        "failures": failures,
        "inner_split": split_summary,
        "research_metadata": {
            "category_coverage": sorted(evaluation_cases["category"].astype(str).unique()),
            "data_source": manifest.get("source_name", "unknown"),
            "data_source_revision": manifest.get("source_revision", "unknown"),
            "evidence_provider": type(evidence_provider).__name__,
            "forecast_end": format_utc(forecast_end.to_pydatetime()),
            "forecast_start": format_utc(forecast_start.to_pydatetime()),
            "forecast_timestamp_policy": "verified forecasted_at from frozen dataset",
            "known_exclusions": [
                "Failed forecasts are excluded from evaluator metrics but remain in the "
                "experiment denominator and failure ledger.",
                "Inner validation, when enabled, purges parent groups observed in inner "
                "development.",
                "No final holdout rows are accepted by this development-only runner.",
            ],
            "maximum_forecast_horizon_days": float(horizon_days.max()),
            "maximum_market_price_staleness_hours": float(market_staleness_hours.max()),
            "minimum_forecast_horizon_days": float(horizon_days.min()),
            "parent_event_count": int(evaluation_cases[config.parent_group_column].nunique()),
            "research_cutoff_policy": config.research_cutoff_policy,
        },
        "model_metadata": adapter.metadata.to_dict(),
        "schema_version": 1,
        "source_manifest": manifest,
    }
    report_content_hash = content_hash(summary)
    report_path = output_root / "reports" / f"{report_content_hash}.json"
    write_immutable_json(report_path, summary)
    return summary, report_path