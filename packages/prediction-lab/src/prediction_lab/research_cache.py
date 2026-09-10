from __future__ import annotations

import json
from pathlib import Path

from prediction_lab.research_types import (
    EvidencePacket,
    ForecastArtifact,
    ResearchContractError,
    canonical_json_bytes,
    content_hash,
)


def write_immutable_json(path: str | Path, value: object) -> None:
    """Write a canonical content-addressed file, refusing conflicting replacement."""

    destination = Path(path)
    payload = canonical_json_bytes(value) + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != payload:
            raise ResearchContractError(f"Refusing to overwrite immutable artifact {destination}")
        return
    destination.write_bytes(payload)


def forecast_cache_key(
    *,
    code_commit: str,
    model_request_hash: str,
    evidence_packet_hash: str,
    prompt_version: str,
    model_metadata: object,
    mode: str,
    experiment_config_hash: str,
) -> str:
    return content_hash(
        {
            "code_commit": code_commit,
            "evidence_packet_hash": evidence_packet_hash,
            "experiment_config_hash": experiment_config_hash,
            "mode": mode,
            "model_metadata": model_metadata,
            "model_request_hash": model_request_hash,
            "prompt_version": prompt_version,
        }
    )


class FilesystemForecastCache:
    """Simple content-addressed cache with cutoff and integrity checks on reads."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise ResearchContractError("Cache key must be a lowercase SHA-256 digest")
        return self.root / key[:2] / f"{key}.json"

    def load(
        self,
        key: str,
        *,
        evidence_packet: EvidencePacket,
        forecast_cutoff_at: object,
    ) -> ForecastArtifact | None:
        evidence_packet.assert_safe_for_cutoff(forecast_cutoff_at)
        path = self._path(key)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchContractError(f"Invalid forecast cache entry {path}") from exc
        if not isinstance(raw, dict):
            raise ResearchContractError(f"Invalid forecast cache entry {path}")
        artifact = ForecastArtifact.from_dict(raw)
        if artifact.cache_key != key:
            raise ResearchContractError("Forecast cache key mismatch")
        if artifact.evidence_packet_hash != evidence_packet.packet_hash:
            raise ResearchContractError("Forecast cache evidence packet mismatch")
        return artifact

    def store(self, artifact: ForecastArtifact) -> Path:
        path = self._path(artifact.cache_key)
        write_immutable_json(path, artifact.to_dict())
        return path
