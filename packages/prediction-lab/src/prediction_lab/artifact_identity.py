"""Verify exact GitHub artifact identities and archive bytes before extraction."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from prediction_lab.research_types import ResearchContractError

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def select_artifact(
    pages: object,
    *,
    name: str,
    run_id: int,
    digest: str,
    code_commit: str | None = None,
) -> dict[str, Any]:
    if not _SHA256.fullmatch(digest):
        raise ResearchContractError("Expected artifact digest must be sha256:<64 hex>")
    if not isinstance(pages, list):
        raise ResearchContractError("Malformed GitHub artifact pages")
    matches: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("artifacts"), list):
            raise ResearchContractError("Malformed GitHub artifact listing")
        matches.extend(
            item
            for item in page["artifacts"]
            if isinstance(item, dict) and item.get("name") == name
        )
    if len(matches) != 1:
        raise ResearchContractError("Expected exactly one immutable named artifact")
    item = matches[0]
    identity = item.get("id")
    if isinstance(identity, bool) or not isinstance(identity, int) or identity < 1:
        raise ResearchContractError("Artifact has no immutable numeric identity")
    if item.get("expired") is not False:
        raise ResearchContractError("Artifact is expired or expiry state is unknown")
    if item.get("digest") != digest:
        raise ResearchContractError(
            "Artifact digest is unavailable or differs from preregistration"
        )
    workflow = item.get("workflow_run")
    if not isinstance(workflow, dict) or workflow.get("id") != run_id:
        raise ResearchContractError("Artifact workflow identity mismatch")
    if code_commit is not None and workflow.get("head_sha") != code_commit:
        raise ResearchContractError("Artifact source commit mismatch")
    return item


def extract_verified_archive(
    payload: bytes,
    *,
    digest: str,
    destination: Path,
    allowed_files: frozenset[str],
) -> None:
    if "sha256:" + hashlib.sha256(payload).hexdigest() != digest:
        raise ResearchContractError("Downloaded artifact archive digest mismatch")
    if destination.exists():
        raise ResearchContractError("Refusing to replace an existing artifact directory")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(names) != len(set(names)) or not set(names).issubset(allowed_files):
            raise ResearchContractError("Artifact contains duplicate or non-allowlisted members")
        if any(
            member.is_dir() or (member.external_attr >> 16) & 0o170000 == 0o120000
            for member in members
        ):
            raise ResearchContractError("Artifact contains unsupported directory/link members")
        # Names are exact allowlisted basenames, never archive-controlled paths.
        if any(Path(name).name != name or "/" in name or "\\" in name for name in names):
            raise ResearchContractError("Artifact member is not a basename")
        contents = {name: archive.read(name) for name in names}  # CRC verification before writes
    destination.mkdir(parents=True)
    for name, content in contents.items():
        (destination / name).write_bytes(content)


def download_verified_artifact(
    *,
    repository: str,
    run_id: int,
    name: str,
    digest: str,
    destination: Path,
    allowed_files: frozenset[str],
    code_commit: str | None = None,
) -> None:
    gh = shutil.which("gh")
    if gh is None:
        raise ResearchContractError("GitHub CLI is required for artifact verification")
    listing = subprocess.run(  # noqa: S603 - resolved executable, no shell
        [gh, "api", f"repos/{repository}/actions/runs/{run_id}/artifacts", "--paginate", "--slurp"],
        check=True,
        capture_output=True,
    )
    item = select_artifact(
        json.loads(listing.stdout), name=name, run_id=run_id, digest=digest, code_commit=code_commit
    )
    archive = subprocess.run(  # noqa: S603 - download by verified immutable numeric ID
        [gh, "api", f"repos/{repository}/actions/artifacts/{item['id']}/zip"],
        check=True,
        capture_output=True,
    )
    extract_verified_archive(
        archive.stdout, digest=digest, destination=destination, allowed_files=allowed_files
    )
    proof = {
        "artifact_id": item["id"],
        "name": name,
        "run_id": run_id,
        "archive_sha256": digest,
        "workflow_run": item["workflow_run"],
    }
    destination.with_suffix(".identity.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
