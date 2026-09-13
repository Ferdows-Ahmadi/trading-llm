from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from prediction_lab.artifact_identity import extract_verified_archive, select_artifact
from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.local_development_cli import (
    FROZEN_MODEL_DIGEST,
    _build_model_metadata,
    _ensure_model,
    _validate_frozen_inputs,
)
from prediction_lab.research_types import EvidenceItem, ResearchContractError, content_hash


def _fixture() -> dict:
    item = EvidenceItem.create(
        source_id="source",
        source_type="test",
        uri_or_reference="test://x",
        title="Historical title",
        available_at="2025-01-01T00:00:00Z",
        retrieved_at="2026-01-01T00:00:00Z",
        text="Unchanged body",
    )
    return {"schema_version": 1, "questions": {"q": [item.to_dict()]}}


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "Changed title"),
        ("available_at", "2024-01-01T00:00:00Z"),
        ("source_id", "different"),
        ("text", "Changed body"),
    ],
)
def test_fixture_hash_covers_actual_metadata_and_body(
    tmp_path: Path, field: str, value: str
) -> None:
    payload = _fixture()
    digest = content_hash(payload)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert FileEvidenceProvider(path, expected_fixture_hash=digest).fixture_hash == digest
    payload["questions"]["q"][0][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResearchContractError, match="Canonical"):
        FileEvidenceProvider(path, expected_fixture_hash=digest)


def test_fixture_canonical_hash_ignores_serialization_whitespace(tmp_path: Path) -> None:
    payload = _fixture()
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload, indent=4, sort_keys=False), encoding="utf-8")
    FileEvidenceProvider(path, expected_fixture_hash=content_hash(payload))


def _artifact() -> dict:
    return {
        "id": 123,
        "name": "development",
        "digest": "sha256:" + "a" * 64,
        "expired": False,
        "workflow_run": {"id": 456, "head_sha": "b" * 40},
    }


@pytest.mark.parametrize(
    "change",
    [
        {"digest": None},
        {"digest": "sha256:" + "c" * 64},
        {"expired": True},
        {"expired": None},
        {"id": True},
        {"id": 0},
        {"workflow_run": {"id": 999}},
        {"workflow_run": {"id": 456, "head_sha": "c" * 40}},
    ],
)
def test_artifact_identity_rejects_unavailable_or_changed_provenance(change: dict) -> None:
    item = _artifact() | change
    with pytest.raises(ResearchContractError):
        select_artifact(
            [{"artifacts": [item]}],
            name="development",
            run_id=456,
            digest="sha256:" + "a" * 64,
            code_commit="b" * 40,
        )


def test_artifact_identity_pagination_and_duplicates() -> None:
    item = _artifact()
    assert (
        select_artifact(
            [{"artifacts": []}, {"artifacts": [item]}],
            name="development",
            run_id=456,
            digest=item["digest"],
            code_commit="b" * 40,
        )
        == item
    )
    for items in ([], [item, item]):
        with pytest.raises(ResearchContractError, match="exactly one"):
            select_artifact(
                [{"artifacts": items}], name="development", run_id=456, digest=item["digest"]
            )


def _zip(name: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(name, "synthetic data")
    return stream.getvalue()


def test_archive_bytes_verified_before_extraction(tmp_path: Path) -> None:
    payload = _zip("development.csv")
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    output = tmp_path / "output"
    with pytest.raises(ResearchContractError, match="digest mismatch"):
        extract_verified_archive(
            payload + b"tamper",
            digest=digest,
            destination=output,
            allowed_files=frozenset({"development.csv"}),
        )
    assert not output.exists()
    extract_verified_archive(
        payload, digest=digest, destination=output, allowed_files=frozenset({"development.csv"})
    )
    assert (output / "development.csv").read_text() == "synthetic data"
    with pytest.raises(ResearchContractError, match="replace"):
        extract_verified_archive(
            payload, digest=digest, destination=output, allowed_files=frozenset({"development.csv"})
        )


@pytest.mark.parametrize("name", ["../escape", "extra.csv", "folder/data", "folder\\data"])
def test_archive_rejects_non_allowlisted_members(tmp_path: Path, name: str) -> None:
    payload = _zip(name)
    with pytest.raises(ResearchContractError, match="allowlisted"):
        extract_verified_archive(
            payload,
            digest="sha256:" + hashlib.sha256(payload).hexdigest(),
            destination=tmp_path / "output",
            allowed_files=frozenset({"data"}),
        )
    assert not (tmp_path / "output").exists()


def test_model_provenance_cannot_be_assigned_to_another_digest(tmp_path: Path) -> None:
    with pytest.raises(ResearchContractError, match="unregistered digest"):
        _build_model_metadata(tmp_path, "sha256:" + "a" * 64)


def test_wrong_model_fails_before_pull(tmp_path: Path) -> None:
    with pytest.raises(ResearchContractError, match="model tag"):
        _ensure_model(
            repository_root=tmp_path, model="other:latest", base_url="unused", refresh=False
        )


def test_runner_detects_tampered_fixture_even_with_unchanged_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pandas as pd

    import prediction_lab.local_development_cli as cli

    pilot, evidence = tmp_path / "pilot", tmp_path / "evidence"
    pilot.mkdir()
    evidence.mkdir()
    frame = pd.DataFrame({"question_id": [f"q{i}" for i in range(20)], "split": "development"})
    monkeypatch.setattr(cli, "verify_frozen_dataset", lambda **kwargs: frame)
    (pilot / "development-pilot.manifest.json").write_text(
        json.dumps({"sha256": cli.PILOT_DATASET_SHA256})
    )
    fixture = {"schema_version": 1, "questions": {f"q{i}": [] for i in range(20)}}
    fixture["questions"]["q0"] = _fixture()["questions"]["q"]
    digest = content_hash(fixture)
    spec = {"filtered_fixture_sha256": digest, "expected_summary": {"pilot_questions": 20}}
    (evidence / "relevance-summary.json").write_text(
        json.dumps(
            {
                "filtered_fixture_hash": digest,
                "pilot_questions": 20,
            }
        )
    )
    path = evidence / "evidence-fixture.filtered.json"
    path.write_text(json.dumps(fixture))
    _validate_frozen_inputs(pilot, evidence, spec)
    tampered = copy.deepcopy(fixture)
    tampered["questions"]["q0"][0]["title"] = "Metadata tampering"
    path.write_text(json.dumps(tampered))
    with pytest.raises(ResearchContractError, match="Canonical"):
        _validate_frozen_inputs(pilot, evidence, spec)
    assert FROZEN_MODEL_DIGEST == (
        "sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e"
    )


def test_download_uses_verified_numeric_identity_and_checks_archive(tmp_path, monkeypatch):
    import subprocess

    from prediction_lab.artifact_identity import download_verified_artifact

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("fixture.json", "{}")
    archive_bytes = stream.getvalue()
    digest = "sha256:" + hashlib.sha256(archive_bytes).hexdigest()
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps([{"artifacts": [_artifact() | {"digest": digest}]}]).encode(),
            )
        assert args[-1] == "repos/test/repo/actions/artifacts/123/zip"
        return subprocess.CompletedProcess(args, 0, stdout=archive_bytes)

    monkeypatch.setattr("prediction_lab.artifact_identity.shutil.which", lambda name: "gh.exe")
    monkeypatch.setattr("prediction_lab.artifact_identity.subprocess.run", run)
    download_verified_artifact(
        repository="test/repo",
        run_id=456,
        name="development",
        digest=digest,
        destination=tmp_path / "artifact",
        allowed_files=frozenset({"fixture.json"}),
    )
    assert (tmp_path / "artifact" / "fixture.json").read_text() == "{}"
    assert json.loads((tmp_path / "artifact.identity.json").read_text())["artifact_id"] == 123
    assert calls[0][-2:] == ["--paginate", "--slurp"]


@pytest.mark.parametrize("tamper", ["raw", "text", "identity"])
def test_cached_content_digest_and_identity_tampering(tmp_path, tamper):
    import httpx
    from test_wayback_content import test_freeze_wayback_content_builds_hashed_evidence_fixture

    from prediction_lab.wayback_content import WaybackReplayClient, freeze_wayback_content

    test_freeze_wayback_content_builds_hashed_evidence_fixture(tmp_path)
    frozen = tmp_path / "frozen"

    def never(request):
        raise AssertionError("Cache verification must not fetch")

    def freeze():
        with httpx.Client(transport=httpx.MockTransport(never)) as client:
            return freeze_wayback_content(
                captures_jsonl=tmp_path / "captures.jsonl",
                output_directory=frozen,
                replay_client=WaybackReplayClient(client=client),
            )

    assert freeze()["reused_checkpoints"] == 1
    if tamper == "identity":
        path = next((frozen / "checkpoints").glob("*.json"))
        payload = json.loads(path.read_text())
        payload["record"]["question_id"] = "other"
        path.write_text(json.dumps(payload))
    else:
        path = next((frozen / tamper).iterdir())
        path.write_text("corrupted")
    with pytest.raises(ResearchContractError):
        freeze()
