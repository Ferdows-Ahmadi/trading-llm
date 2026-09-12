from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.experiments import run_development_experiment
from prediction_lab.local_development_cli import (
    DEFAULT_MODEL,
    PILOT_ARTIFACT,
    PILOT_ARTIFACT_DIGEST,
    PILOT_DATASET_SHA256,
    PILOT_RUN_ID,
    _assert_clean_research_checkout,
    _assert_loopback_ollama,
    _assert_work_root_outside_repository,
    _build_model_metadata,
    _download_frozen_inputs,
    _ensure_model,
    _fetch_ollama_tags,
    _load_evidence_spec,
    _report_payload,
    _select_model_digest,
    _validate_frozen_inputs,
)
from prediction_lab.ollama_adapter import OllamaStructuredModelAdapter
from prediction_lab.residual_adapter import (
    MAX_ABS_LOGIT_DELTA,
    RESIDUAL_MAPPING_VERSION,
    STRENGTH_TO_ABS_DELTA,
    OllamaMarketResidualAdapter,
)
from prediction_lab.research_types import ResearchContractError, content_hash

PREREGISTRATION_COMMIT = "271a0866d1c2ebd4ffa70275f7d187e776fcdc75"
DEFAULT_EVIDENCE_SPEC = Path("docs/experiments/evidence-relevance-v2-canonical.json")
EXPECTED_EVIDENCE = {
    "schema_version": 1,
    "workflow_run": 34689232387,
    "artifact": "evidence-relevance-filter-v0.2",
    "artifact_digest": "sha256:1d0280f73d0a48f925dd4ef5f48ab6328a5f7d16ea295d4f78fadcd7e741c0e4",
    "filtered_fixture_sha256": "cfafa8c780c7067c656a5c8474f172f46239f12e10f1632cd22256f2430a3035",
    "artifact_code_commit": "700353ec323ab7a0274197ae8e3996761babf4ec",
    "preregistration_commit": "651a65d00db80ea194e4a95d314bb6ebd03a29f5",
    "expected_summary": {
        "method_version": "lexical-relevance-v2",
        "pilot_questions": 20,
        "raw_items": 94,
        "kept_items": 7,
        "questions_with_kept": 4,
        "questions_without_kept": 16,
        "max_items_per_question": 5,
        "lead_words": 40,
        "intent_window_words": 50,
        "min_body_subject_mentions": 2,
    },
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the preregistered relevance-v2 market-residual-v1 development experiment. "
            "This command never downloads or opens holdout data."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--ollama-model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-timeout-seconds", type=float, default=240.0)
    parser.add_argument("--evidence-spec", type=Path, default=DEFAULT_EVIDENCE_SPEC)
    parser.add_argument(
        "--refresh-model",
        action="store_true",
        help="Pull the requested Ollama tag even when it is already installed locally.",
    )
    return parser


def _assert_preregistered_evidence_spec(spec: dict[str, object]) -> None:
    if spec != EXPECTED_EVIDENCE:
        raise ResearchContractError(
            "market-residual-v1 requires the exact frozen relevance-v2 evidence lineage"
        )


def run_residual_development(args: argparse.Namespace) -> Path:
    repository_root = args.repository_root.resolve()
    _assert_loopback_ollama(args.ollama_base_url)
    _, code_commit = _assert_clean_research_checkout(repository_root)
    evidence_spec = _load_evidence_spec(repository_root, args.evidence_spec)
    _assert_preregistered_evidence_spec(evidence_spec)

    default_work_root = repository_root.parent / "trading-llm-residual-runs"
    requested_work_root = args.work_root or default_work_root
    work_root = _assert_work_root_outside_repository(repository_root, requested_work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = work_root / f"llama31-market-residual-v1-{timestamp}-{code_commit[:12]}"
    run_root.mkdir(parents=False, exist_ok=False)

    pilot_dir, evidence_dir = _download_frozen_inputs(
        repository_root=repository_root,
        run_root=run_root,
        evidence_spec=evidence_spec,
    )
    pilot_csv, pilot_manifest, evidence_fixture = _validate_frozen_inputs(
        pilot_dir,
        evidence_dir,
        evidence_spec,
    )

    immutable_digest = _ensure_model(
        repository_root=repository_root,
        model=args.ollama_model,
        base_url=args.ollama_base_url,
        refresh=args.refresh_model,
    )
    metadata = _build_model_metadata(repository_root, immutable_digest)
    (run_root / "model-metadata.json").write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _, checked_commit = _assert_clean_research_checkout(repository_root)
    if checked_commit != code_commit:
        raise ResearchContractError("Repository HEAD changed while preparing residual run")

    blind_adapter = OllamaStructuredModelAdapter(
        model=args.ollama_model,
        metadata=metadata,
        base_url=args.ollama_base_url,
        timeout_seconds=args.ollama_timeout_seconds,
    )
    residual_adapter = OllamaMarketResidualAdapter(
        model=args.ollama_model,
        metadata=metadata,
        base_url=args.ollama_base_url,
        timeout_seconds=args.ollama_timeout_seconds,
    )
    outputs: dict[str, object] = {}
    try:
        _, blind_report = run_development_experiment(
            development_csv=pilot_csv,
            development_manifest=pilot_manifest,
            evidence_provider=FileEvidenceProvider(evidence_fixture),
            adapter=blind_adapter,
            output_directory=run_root / "blind",
            experiment_id="llama31-8b-market-residual-v1-blind-control",
            hypothesis=(
                "The preregistered bounded market-residual architecture may improve "
                "market-aware forecasts while the blind research-v0 control remains unchanged."
            ),
            prompt_version="research-v0",
            mode="blind",
            repository_root=repository_root,
        )
        outputs["blind"] = _report_payload(blind_report)

        _, checked_commit = _assert_clean_research_checkout(repository_root)
        if checked_commit != code_commit:
            raise ResearchContractError("Repository HEAD changed during residual run")

        _, market_report = run_development_experiment(
            development_csv=pilot_csv,
            development_manifest=pilot_manifest,
            evidence_provider=FileEvidenceProvider(evidence_fixture),
            adapter=residual_adapter,
            output_directory=run_root / "market-aware",
            experiment_id="llama31-8b-market-residual-v1-market-aware",
            hypothesis=(
                "A preregistered bounded logit residual applied only to relevance-v2 evidence "
                "may improve on the contemporaneous prediction-market baseline."
            ),
            prompt_version="market-residual-v1",
            mode="market-aware",
            repository_root=repository_root,
        )
        outputs["market-aware"] = _report_payload(market_report)
    finally:
        blind_adapter.close()
        residual_adapter.close()

    decisions = residual_adapter.decision_records()
    if len(decisions) != 20:
        raise ResearchContractError(
            f"Residual decision ledger must contain 20 questions; found {len(decisions)}"
        )
    hard_noops = sum(record.get("hard_noop") is True for record in decisions.values())
    if hard_noops != 16:
        raise ResearchContractError(
            f"Relevance-v2 requires 16 deterministic zero-evidence no-ops; found {hard_noops}"
        )
    decision_path = run_root / "residual-decisions.json"
    decision_path.write_text(
        json.dumps(decisions, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    final_digest = _select_model_digest(_fetch_ollama_tags(args.ollama_base_url), args.ollama_model)
    if final_digest != immutable_digest:
        raise ResearchContractError("Ollama model digest changed during residual scoring")
    _, final_commit = _assert_clean_research_checkout(repository_root)
    if final_commit != code_commit:
        raise ResearchContractError("Repository HEAD changed before residual experiment finished")

    result = {
        "schema_version": 1,
        "experiment": "llama31-8b-market-residual-v1",
        "dataset_role": "development-only",
        "holdout_accessed": False,
        "code_commit": code_commit,
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "model_tag": args.ollama_model,
        "model_immutable_version": immutable_digest,
        "prompt_versions": {
            "blind": "research-v0",
            "market-aware": "market-residual-v1",
        },
        "residual_mapping": {
            "mapping_version": RESIDUAL_MAPPING_VERSION,
            "max_abs_logit_delta": MAX_ABS_LOGIT_DELTA,
            "strength_to_abs_logit_delta": STRENGTH_TO_ABS_DELTA,
            "zero_evidence_policy": "hard-noop-without-model-call",
        },
        "residual_decisions_sha256": content_hash(decisions),
        "residual_decision_counts": {
            "total": len(decisions),
            "hard_noop": hard_noops,
            "model_evaluated": len(decisions) - hard_noops,
        },
        "inputs": {
            "development_pilot": {
                "workflow_run": PILOT_RUN_ID,
                "artifact": PILOT_ARTIFACT,
                "artifact_digest": PILOT_ARTIFACT_DIGEST,
                "dataset_sha256": PILOT_DATASET_SHA256,
            },
            "filtered_evidence": evidence_spec,
        },
        "modes": outputs,
    }
    summary_path = run_root / "local-development-summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def main() -> None:
    args = _build_parser().parse_args()
    summary_path = run_residual_development(args)
    print(f"Residual development experiment summary: {summary_path}")
    print(summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
