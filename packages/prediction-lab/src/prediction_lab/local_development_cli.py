from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from prediction_lab.datasets import verify_frozen_dataset
from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.experiments import run_development_experiment
from prediction_lab.ollama_adapter import OllamaStructuredModelAdapter
from prediction_lab.research_types import ModelMetadata, ResearchContractError

REPOSITORY = "Ferdows-Ahmadi/trading-llm"
ACTIVE_BRANCH = "research/prediction-market-lab-v0.1"
PILOT_RUN_ID = 34555783305
PILOT_ARTIFACT = "prediction-lab-development-pilot-v0.1"
PILOT_ARTIFACT_DIGEST = "sha256:c8b24dd5b92fd36625d756ea4f94d98841ce8303757190d2c6385c27276032c7"
PILOT_DATASET_SHA256 = "d27e2b84cf1f3bc9bdeb4904e15791aad5d2e586685b7f32ab1647d15eee41ce"
EVIDENCE_RUN_ID = 34529685281
EVIDENCE_ARTIFACT = "evidence-relevance-filter-v0.1"
EVIDENCE_ARTIFACT_DIGEST = (
    "sha256:bf76e2545f3cf30b89199b64c51c109ab51cc0c6cd7b5e3c3c9481be5a285aec"
)
FILTERED_FIXTURE_SHA256 = "6c5d203feb47b13f15cfe46bbf58d327629544bd9aba61bfed140c30feb92108"
PROVENANCE_PATH = Path("docs/models/meta-llama-3.1-8b-instruct-provenance.json")
DEFAULT_MODEL = "llama3.1:8b"
_DIGEST_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen 20-question development experiment locally with Llama 3.1 8B "
            "through Ollama. This command never downloads or opens holdout data."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--ollama-model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--ollama-timeout-seconds", type=float, default=240.0)
    parser.add_argument(
        "--evidence-spec",
        type=Path,
        help=(
            "Optional checked-in JSON lineage spec for an alternate frozen development "
            "evidence artifact. When omitted, the original relevance-v1 artifact is used."
        ),
    )
    parser.add_argument(
        "--refresh-model",
        action="store_true",
        help="Pull the requested Ollama tag even when it is already installed locally.",
    )
    return parser


def _which(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise ResearchContractError(f"Required executable is not on PATH: {name}")
    return executable


def _capture(executable: str, args: list[str], *, cwd: Path) -> str:
    try:
        completed = subprocess.run(  # noqa: S603
            [executable, *args],
            cwd=cwd,
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ResearchContractError(f"Command failed: {detail}") from exc
    return completed.stdout.strip()


def _run(executable: str, args: list[str], *, cwd: Path) -> None:
    try:
        subprocess.run([executable, *args], cwd=cwd, check=True)  # noqa: S603
    except subprocess.CalledProcessError as exc:
        raise ResearchContractError(f"Command failed with exit code {exc.returncode}") from exc


def _assert_clean_research_checkout(repository_root: Path) -> tuple[str, str]:
    repository_root = repository_root.resolve()
    git = _which("git")
    branch = _capture(git, ["branch", "--show-current"], cwd=repository_root)
    if branch != ACTIVE_BRANCH:
        raise ResearchContractError(
            f"Local development run requires branch {ACTIVE_BRANCH!r}; found {branch!r}"
        )
    dirty = _capture(git, ["status", "--porcelain"], cwd=repository_root)
    if dirty:
        raise ResearchContractError(
            "Local development run requires a clean worktree so code provenance is exact"
        )
    head = _capture(git, ["rev-parse", "HEAD"], cwd=repository_root)
    if not _COMMIT_RE.fullmatch(head):
        raise ResearchContractError(f"Unexpected Git HEAD: {head!r}")
    return git, head


def _assert_work_root_outside_repository(repository_root: Path, work_root: Path) -> Path:
    repository_root = repository_root.resolve()
    resolved = work_root.resolve()
    if resolved == repository_root or resolved.is_relative_to(repository_root):
        raise ResearchContractError(
            "Research inputs and outputs must live outside the Git checkout to keep it clean"
        )
    return resolved


def _assert_loopback_ollama(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ResearchContractError("Ollama base URL must use http or https")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ResearchContractError(
            "Scientific local run requires a loopback Ollama endpoint; "
            "remote model endpoints are blocked"
        )


def _normalize_digest(value: object) -> str:
    match = _DIGEST_RE.fullmatch(str(value).strip())
    if match is None:
        raise ResearchContractError(f"Ollama returned an invalid model digest: {value!r}")
    return f"sha256:{match.group(1)}"


def _select_model_digest(payload: object, model: str) -> str | None:
    if not isinstance(payload, dict):
        raise ResearchContractError("Ollama /api/tags response must be a JSON object")
    models = payload.get("models")
    if not isinstance(models, list):
        raise ResearchContractError("Ollama /api/tags response is missing models")

    matches: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        names = {str(item.get("name", "")), str(item.get("model", ""))}
        if model not in names:
            continue
        matches.add(_normalize_digest(item.get("digest")))

    if not matches:
        return None
    if len(matches) != 1:
        raise ResearchContractError(f"Ollama tag {model!r} resolved to multiple digests")
    return next(iter(matches))


def _fetch_ollama_tags(base_url: str) -> object:
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.get(f"{base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise ResearchContractError(
            f"Cannot read local Ollama model inventory at {base_url}: {exc}"
        ) from exc


def _ensure_model(
    *,
    repository_root: Path,
    model: str,
    base_url: str,
    refresh: bool,
) -> str:
    ollama = _which("ollama")
    digest = _select_model_digest(_fetch_ollama_tags(base_url), model)
    if refresh or digest is None:
        _run(ollama, ["pull", model], cwd=repository_root)
        digest = _select_model_digest(_fetch_ollama_tags(base_url), model)
    if digest is None:
        raise ResearchContractError(f"Ollama model {model!r} is not installed after pull")
    return digest


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchContractError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchContractError(f"Expected JSON object in {path}")
    return value


def _default_evidence_spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_run": EVIDENCE_RUN_ID,
        "artifact": EVIDENCE_ARTIFACT,
        "artifact_digest": EVIDENCE_ARTIFACT_DIGEST,
        "filtered_fixture_sha256": FILTERED_FIXTURE_SHA256,
        "expected_summary": {
            "method_version": "lexical-relevance-v1",
            "pilot_questions": 20,
            "raw_items": 94,
            "kept_items": 16,
            "questions_with_kept": 8,
            "questions_without_kept": 12,
        },
    }


def _load_evidence_spec(repository_root: Path, spec_path: Path | None) -> dict[str, object]:
    if spec_path is None:
        spec = _default_evidence_spec()
    else:
        resolved = spec_path if spec_path.is_absolute() else repository_root / spec_path
        spec = _load_json(resolved)

    if spec.get("schema_version") != 1:
        raise ResearchContractError("Evidence lineage spec must use schema_version 1")
    workflow_run = spec.get("workflow_run")
    if not isinstance(workflow_run, int) or workflow_run < 1:
        raise ResearchContractError("Evidence lineage spec workflow_run must be a positive integer")
    artifact = spec.get("artifact")
    if not isinstance(artifact, str) or not artifact.strip():
        raise ResearchContractError("Evidence lineage spec artifact must be a non-empty string")
    artifact_digest = spec.get("artifact_digest")
    if _DIGEST_RE.fullmatch(str(artifact_digest).strip()) is None:
        raise ResearchContractError("Evidence lineage spec artifact_digest is invalid")
    fixture_hash = spec.get("filtered_fixture_sha256")
    if _DIGEST_RE.fullmatch(str(fixture_hash).strip()) is None:
        raise ResearchContractError("Evidence lineage spec filtered_fixture_sha256 is invalid")
    expected_summary = spec.get("expected_summary")
    if not isinstance(expected_summary, dict) or not expected_summary:
        raise ResearchContractError("Evidence lineage spec expected_summary must be a non-empty object")

    for key in ("artifact_code_commit", "preregistration_commit"):
        value = spec.get(key)
        if value is not None and not _COMMIT_RE.fullmatch(str(value)):
            raise ResearchContractError(f"Evidence lineage spec {key} is not a Git commit SHA")
    return spec


def _download_frozen_inputs(
    *,
    repository_root: Path,
    run_root: Path,
    evidence_spec: dict[str, object],
) -> tuple[Path, Path]:
    gh = _which("gh")
    inputs = run_root / "inputs"
    pilot_dir = inputs / "development-pilot"
    evidence_dir = inputs / "filtered-evidence"
    inputs.mkdir(parents=True, exist_ok=False)

    _run(
        gh,
        [
            "run",
            "download",
            str(PILOT_RUN_ID),
            "-R",
            REPOSITORY,
            "-n",
            PILOT_ARTIFACT,
            "-D",
            str(pilot_dir),
        ],
        cwd=repository_root,
    )
    _run(
        gh,
        [
            "run",
            "download",
            str(evidence_spec["workflow_run"]),
            "-R",
            REPOSITORY,
            "-n",
            str(evidence_spec["artifact"]),
            "-D",
            str(evidence_dir),
        ],
        cwd=repository_root,
    )
    return pilot_dir, evidence_dir


def _validate_frozen_inputs(
    pilot_dir: Path,
    evidence_dir: Path,
    evidence_spec: dict[str, object],
) -> tuple[Path, Path, Path]:
    forbidden = [
        path
        for directory in (pilot_dir, evidence_dir)
        for path in directory.rglob("holdout*")
    ]
    if forbidden:
        raise ResearchContractError(
            f"Holdout material found in local development inputs: {forbidden}"
        )

    pilot_csv = pilot_dir / "development-pilot.csv"
    pilot_manifest = pilot_dir / "development-pilot.manifest.json"
    evidence_fixture = evidence_dir / "evidence-fixture.filtered.json"
    relevance_summary = evidence_dir / "relevance-summary.json"

    manifest = _load_json(pilot_manifest)
    if manifest.get("sha256") != PILOT_DATASET_SHA256:
        raise ResearchContractError("Frozen development-pilot dataset hash changed")
    frame = verify_frozen_dataset(csv_path=pilot_csv, manifest_path=pilot_manifest)
    if len(frame) != 20 or frame["question_id"].nunique() != 20:
        raise ResearchContractError("Development pilot is not exactly 20 unique questions")
    if set(frame["split"].astype(str)) != {"development"}:
        raise ResearchContractError("Development pilot contains a non-development row")

    relevance = _load_json(relevance_summary)
    expected_fixture_hash = str(evidence_spec["filtered_fixture_sha256"])
    if relevance.get("filtered_fixture_hash") != expected_fixture_hash:
        raise ResearchContractError("Frozen filtered-evidence fixture identity changed")
    expected_relevance = evidence_spec["expected_summary"]
    if not isinstance(expected_relevance, dict):
        raise ResearchContractError("Evidence lineage expected_summary is invalid")
    for key, expected in expected_relevance.items():
        if relevance.get(key) != expected:
            raise ResearchContractError(
                f"Frozen relevance summary changed for {key}: {relevance.get(key)!r}"
            )

    marker_expectations = {
        "code-commit.txt": evidence_spec.get("artifact_code_commit"),
        "preregistration-commit.txt": evidence_spec.get("preregistration_commit"),
    }
    for filename, expected in marker_expectations.items():
        if expected is None:
            continue
        marker = evidence_dir / filename
        try:
            actual = marker.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ResearchContractError(f"Missing frozen evidence marker {filename}") from exc
        if actual != expected:
            raise ResearchContractError(
                f"Frozen evidence marker {filename} changed: {actual!r}"
            )

    fixture = _load_json(evidence_fixture)
    FileEvidenceProvider(evidence_fixture)
    questions = fixture.get("questions")
    if not isinstance(questions, dict):
        raise ResearchContractError("Filtered evidence fixture is missing questions mapping")
    if set(questions) != set(frame["question_id"].astype(str)):
        raise ResearchContractError("Development pilot and evidence fixture question IDs differ")
    return pilot_csv, pilot_manifest, evidence_fixture


def _build_model_metadata(repository_root: Path, immutable_digest: str) -> ModelMetadata:
    provenance = _load_json(repository_root / PROVENANCE_PATH)
    required = {
        "provider": "Meta",
        "model_id": "Meta-Llama-3.1-8B-Instruct",
        "release_date": "2024-07-23T00:00:00Z",
        "normalized_knowledge_cutoff_upper_bound": "2023-12-31T23:59:59Z",
        "historical_scoring_status": "eligible_after-local-artifact-freeze",
    }
    for key, expected in required.items():
        if provenance.get(key) != expected:
            raise ResearchContractError(
                f"Checked-in Llama provenance changed for {key}: {provenance.get(key)!r}"
            )

    return ModelMetadata.create(
        provider="Meta",
        model_id="Meta-Llama-3.1-8B-Instruct",
        immutable_version=immutable_digest,
        release_date=required["release_date"],
        knowledge_cutoff=required["normalized_knowledge_cutoff_upper_bound"],
        execution_mode="local",
        contamination_assessment="historical-safe",
        contamination_notes=(
            "Meta documents a December 2023 knowledge cutoff. The exact local Ollama model "
            "digest was frozen before scoring. Forecast inference uses the repository's local "
            "Ollama adapter with no tool bindings or web retrieval."
        ),
    )


def _report_payload(report_path: Path) -> dict[str, object]:
    report = _load_json(report_path)
    return {
        "report_content_hash": report_path.stem,
        "run_identity_hash": report.get("run_identity_hash"),
        "experiment_config_hash": report.get("experiment_config_hash"),
        "execution": report.get("execution"),
        "evaluation": report.get("evaluation"),
    }


def run_local_development(args: argparse.Namespace) -> Path:
    repository_root = args.repository_root.resolve()
    _assert_loopback_ollama(args.ollama_base_url)
    _, code_commit = _assert_clean_research_checkout(repository_root)
    evidence_spec = _load_evidence_spec(repository_root, args.evidence_spec)

    default_work_root = repository_root.parent / "trading-llm-local-runs"
    requested_work_root = args.work_root or default_work_root
    work_root = _assert_work_root_outside_repository(repository_root, requested_work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = work_root / f"llama31-development-v0.1-{timestamp}-{code_commit[:12]}"
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
    metadata_path = run_root / "model-metadata.json"
    metadata_path.write_text(
        json.dumps(metadata.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _, checked_commit = _assert_clean_research_checkout(repository_root)
    if checked_commit != code_commit:
        raise ResearchContractError("Repository HEAD changed while preparing the development run")

    outputs: dict[str, object] = {}
    adapter = OllamaStructuredModelAdapter(
        model=args.ollama_model,
        metadata=metadata,
        base_url=args.ollama_base_url,
        timeout_seconds=args.ollama_timeout_seconds,
    )
    try:
        for mode in ("blind", "market-aware"):
            _, checked_commit = _assert_clean_research_checkout(repository_root)
            if checked_commit != code_commit:
                raise ResearchContractError("Repository HEAD changed during the development run")
            summary, report_path = run_development_experiment(
                development_csv=pilot_csv,
                development_manifest=pilot_manifest,
                evidence_provider=FileEvidenceProvider(evidence_fixture),
                adapter=adapter,
                output_directory=run_root / mode,
                experiment_id=f"llama31-8b-development-v0.1-{mode}",
                hypothesis=(
                    "A historically safe Llama 3.1 8B forecast using the frozen pre-cutoff "
                    "evidence may improve probabilistic estimates relative to the "
                    "contemporaneous prediction-market baseline."
                ),
                prompt_version="research-v0",
                mode=mode,
                repository_root=repository_root,
            )
            if summary.get("code_commit") != code_commit:
                raise ResearchContractError(f"{mode} report did not preserve the exact Git commit")
            outputs[mode] = _report_payload(report_path)
    finally:
        adapter.close()

    final_digest = _select_model_digest(_fetch_ollama_tags(args.ollama_base_url), args.ollama_model)
    if final_digest != immutable_digest:
        raise ResearchContractError(
            "Ollama model digest changed during scoring; the experiment is not immutable"
        )
    _, final_commit = _assert_clean_research_checkout(repository_root)
    if final_commit != code_commit:
        raise ResearchContractError("Repository HEAD changed before the experiment finished")

    result = {
        "schema_version": 1,
        "experiment": "llama31-8b-development-v0.1",
        "dataset_role": "development-only",
        "holdout_accessed": False,
        "code_commit": code_commit,
        "model_tag": args.ollama_model,
        "model_immutable_version": immutable_digest,
        "prompt_version": "research-v0",
        "inputs": {
            "development_pilot": {
                "workflow_run": PILOT_RUN_ID,
                "artifact": PILOT_ARTIFACT,
                "artifact_digest": PILOT_ARTIFACT_DIGEST,
                "dataset_sha256": PILOT_DATASET_SHA256,
            },
            "filtered_evidence": {
                "workflow_run": evidence_spec["workflow_run"],
                "artifact": evidence_spec["artifact"],
                "artifact_digest": evidence_spec["artifact_digest"],
                "filtered_fixture_sha256": evidence_spec["filtered_fixture_sha256"],
                "expected_summary": evidence_spec["expected_summary"],
                "artifact_code_commit": evidence_spec.get("artifact_code_commit"),
                "preregistration_commit": evidence_spec.get("preregistration_commit"),
            },
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
    summary_path = run_local_development(args)
    print(f"Local development experiment summary: {summary_path}")
    summary = _load_json(summary_path)
    print(json.dumps(summary.get("modes"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
