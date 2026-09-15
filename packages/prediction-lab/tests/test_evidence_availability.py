from __future__ import annotations

import json
from pathlib import Path

import pytest

from prediction_lab.evidence import FileEvidenceProvider
from prediction_lab.evidence_relevance import filter_evidence_fixture
from prediction_lab.research_cache import FilesystemForecastCache
from prediction_lab.research_forecaster import (
    DeterministicFakeModelAdapter,
    build_model_request,
    forecast_question,
)
from prediction_lab.research_types import (
    EvidenceAvailability,
    EvidenceItem,
    EvidencePacket,
    ResearchContractError,
)


def _item() -> EvidenceItem:
    return EvidenceItem.create(
        source_id="s1",
        source_type="fixture",
        uri_or_reference="fixture://x",
        title="Unrelated",
        available_at="2025-01-01T00:00:00Z",
        retrieved_at="2026-01-01T00:00:00Z",
        text="Historical irrelevant text",
    )


@pytest.mark.parametrize(
    "status,count", [("verified_empty", 1), ("verified_complete", 0), ("invented", 0)]
)
def test_availability_contradictions_fail(status: str, count: int) -> None:
    with pytest.raises(ResearchContractError):
        EvidenceAvailability.from_dict({"status": status, "detail": "test"}, item_count=count)


@pytest.mark.parametrize("status", ["retrieval_failure", "unknown_incomplete"])
@pytest.mark.parametrize("with_items", [True, False])
def test_unverified_evidence_cannot_reach_forecaster(
    tmp_path: Path,
    status: str,
    with_items: bool,
) -> None:
    packet = EvidencePacket.create(
        question_id="q",
        forecasted_at="2025-02-01T00:00:00Z",
        research_cutoff_at="2025-02-01T00:00:00Z",
        evidence_items=[_item()] if with_items else [],
        availability=EvidenceAvailability(status, "failed in 2026"),
    )
    assert EvidencePacket.from_dict(packet.to_dict()) == packet
    with pytest.raises(ResearchContractError, match="not verified"):
        forecast_question(
            experiment_id="synthetic",
            benchmark_hash="test",
            code_commit="test",
            experiment_config_hash="test",
            question_id="q",
            question_text="Test?",
            evidence_packet=packet,
            prompt_version="research-v0",
            mode="market-aware",
            market_probability=0.3,
            adapter=DeterministicFakeModelAdapter(),
            cache=FilesystemForecastCache(tmp_path / "cache"),
        )
    assert not (tmp_path / "cache").exists()


def test_packet_state_is_hashed_but_not_model_facing() -> None:
    args = {
        "question_id": "q",
        "forecasted_at": "2025-02-01T00:00:00Z",
        "research_cutoff_at": "2025-02-01T00:00:00Z",
        "evidence_items": [],
    }
    legacy = EvidencePacket.create(**args)
    verified = EvidencePacket.create(
        **args, availability=EvidenceAvailability("verified_empty", "2026 audit")
    )
    assert legacy.packet_hash != verified.packet_hash
    assert "availability" not in legacy.to_dict()
    assert EvidencePacket.from_dict(legacy.to_dict()).to_dict() == legacy.to_dict()
    request = build_model_request(
        question_id="q",
        question_text="Test?",
        evidence_packet=verified,
        prompt_version="research-v0",
        mode="blind",
        market_probability=None,
    )
    assert "availability" not in json.dumps(request)
    assert "2026 audit" not in json.dumps(request)
    tampered = verified.to_dict()
    tampered["availability"] = {"status": "unknown_incomplete", "detail": "missing"}
    with pytest.raises(ResearchContractError, match="hash mismatch"):
        EvidencePacket.from_dict(tampered)


@pytest.mark.parametrize(
    "states",
    [
        None,
        {},
        {"other": {"status": "verified_empty", "detail": "x"}},
        {"q": {"status": "verified_empty"}},
    ],
)
def test_schema_two_requires_exact_explicit_states(tmp_path: Path, states: object) -> None:
    path = tmp_path / "fixture.json"
    path.write_text(
        json.dumps({"schema_version": 2, "questions": {"q": []}, "availability": states})
    )
    with pytest.raises(ResearchContractError):
        FileEvidenceProvider(path)


@pytest.mark.parametrize("status", ["verified_complete", "retrieval_failure", "unknown_incomplete"])
def test_filter_preserves_failure_state_after_rejecting_all_items(
    tmp_path: Path, status: str
) -> None:
    csv = tmp_path / "development.csv"
    csv.write_text("question_id,question_text\nq,Will Acme launch a token?\n")
    discovery = tmp_path / "discovery.jsonl"
    discovery.write_text('{"question_id":"q"}\n')
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "questions": {"q": [_item().to_dict()]},
                "availability": {"q": {"status": status, "detail": "test"}},
            }
        )
    )
    output = tmp_path / "output"
    filter_evidence_fixture(
        benchmark_csv=csv,
        discovery_jsonl=discovery,
        evidence_fixture=fixture,
        output_directory=output,
    )
    result = json.loads((output / "evidence-fixture.filtered.json").read_text())
    assert result["schema_version"] == 2
    assert result["questions"]["q"] == []
    expected = "verified_empty" if status == "verified_complete" else status
    assert result["availability"]["q"]["status"] == expected


def test_missing_legacy_entry_is_unknown_not_verified_empty(tmp_path: Path) -> None:
    csv = tmp_path / "development.csv"
    csv.write_text("question_id,question_text\nq,Will Acme launch a token?\n")
    discovery = tmp_path / "discovery.jsonl"
    discovery.write_text('{"question_id":"q"}\n')
    fixture = tmp_path / "fixture.json"
    fixture.write_text('{"schema_version":1,"questions":{}}')
    output = tmp_path / "output"
    filter_evidence_fixture(
        benchmark_csv=csv,
        discovery_jsonl=discovery,
        evidence_fixture=fixture,
        output_directory=output,
    )
    provider = FileEvidenceProvider(output / "evidence-fixture.filtered.json")
    packet = provider.build_packet(
        question_id="q",
        forecasted_at="2025-02-01T00:00:00Z",
        research_cutoff_at="2025-02-01T00:00:00Z",
    )
    assert packet.availability.status == "unknown_incomplete"


def test_acquisition_missing_empty_failure_survive_capture_and_freeze(tmp_path):
    import httpx
    from test_evidence_capture_stage import FakeArchive, _freeze_development

    from prediction_lab.evidence_capture_stage import run_commoncrawl_capture_stage
    from prediction_lab.wayback_content import WaybackReplayClient, freeze_wayback_content

    csv, manifest, discovery = _freeze_development(tmp_path)
    records = [json.loads(line) for line in discovery.read_text().splitlines()]
    records = records[:2]  # q-2 discovery is missing, not an empty search result.
    records[0].update(articles=[], acquisition_state="verified", error=None)
    records[1].update(articles=[], acquisition_state="retrieval_failure", error="timeout")
    discovery.write_text("".join(json.dumps(r) + "\n" for r in records))
    output = tmp_path / "captures"
    archive = FakeArchive()
    summary, _ = run_commoncrawl_capture_stage(
        development_csv=csv,
        development_manifest=manifest,
        discovery_jsonl=discovery,
        output_directory=output,
        archive=archive,
        pilot_size=3,
    )
    assert summary["urls_considered"] == 0
    assert archive.calls == 0
    rows = [json.loads(line) for line in (output / "captures.jsonl").read_text().splitlines()]
    assert {r["question_id"]: r["acquisition_state"] for r in rows} == {
        "q-0": "verified",
        "q-1": "retrieval_failure",
        "q-2": "unknown_incomplete",
    }

    def never(request):
        raise AssertionError("No replay call expected")

    with httpx.Client(transport=httpx.MockTransport(never)) as client:
        freeze_wayback_content(
            captures_jsonl=output / "captures.jsonl",
            output_directory=tmp_path / "content",
            replay_client=WaybackReplayClient(client=client),
        )
    fixture = json.loads((tmp_path / "content" / "evidence-fixture.json").read_text())
    assert {q: s["status"] for q, s in fixture["availability"].items()} == {
        "q-0": "verified_empty",
        "q-1": "retrieval_failure",
        "q-2": "unknown_incomplete",
    }


def test_capture_verified_state_survives_new_checkpoints_but_not_legacy(tmp_path):
    from test_evidence_capture_stage import FakeArchive, _freeze_development

    from prediction_lab.evidence_capture_stage import run_commoncrawl_capture_stage

    csv, manifest, discovery = _freeze_development(tmp_path)
    records = [json.loads(line) for line in discovery.read_text().splitlines()]
    for record in records:
        record["acquisition_state"] = "verified"
    discovery.write_text("".join(json.dumps(r) + "\n" for r in records))
    output = tmp_path / "captures"
    kwargs = {
        "development_csv": csv,
        "development_manifest": manifest,
        "discovery_jsonl": discovery,
        "output_directory": output,
        "archive": FakeArchive(),
        "pilot_size": 3,
    }
    for _ in range(2):
        run_commoncrawl_capture_stage(**kwargs)
        assert all(
            json.loads(line)["acquisition_state"] == "verified"
            for line in (output / "captures.jsonl").read_text().splitlines()
        )
    for path in (output / "checkpoints").glob("*.json"):
        payload = json.loads(path.read_text())
        payload.pop("acquisition_context_hash")
        path.write_text(json.dumps(payload))
    run_commoncrawl_capture_stage(**kwargs)
    assert all(
        json.loads(line)["acquisition_state"] == "unknown_incomplete"
        for line in (output / "captures.jsonl").read_text().splitlines()
    )


@pytest.mark.parametrize("fail", [False, True])
def test_all_in_one_producers_distinguish_empty_and_failure(tmp_path, fail):
    from test_commoncrawl_evidence import _freeze_development

    from prediction_lab.commoncrawl_evidence import HistoricalEvidenceError, build_commoncrawl_pilot
    from prediction_lab.gdelt_evidence import build_gdelt_commoncrawl_pilot

    csv, manifest, markets = _freeze_development(tmp_path)

    class EmptyOrFailed:
        def search(self, *args, **kwargs):
            if fail:
                raise HistoricalEvidenceError("synthetic failure")
            return []

        def latest_capture_before(self, *args, **kwargs):
            if fail:
                raise HistoricalEvidenceError("synthetic failure")
            return None

    expected = "retrieval_failure" if fail else "verified_empty"
    fixtures = [
        build_commoncrawl_pilot(
            development_csv=csv,
            development_manifest=manifest,
            source_markets_jsonl=markets,
            client=EmptyOrFailed(),
            pilot_size=4,
        )[0],
        build_gdelt_commoncrawl_pilot(
            development_csv=csv,
            development_manifest=manifest,
            discovery=EmptyOrFailed(),
            archive=EmptyOrFailed(),
            pilot_size=4,
        )[0],
    ]
    for fixture in fixtures:
        assert fixture["schema_version"] == 2
        assert len(fixture["availability"]) == 4
        assert all(state["status"] == expected for state in fixture["availability"].values())


def test_discovery_context_and_legacy_checkpoint_state(tmp_path):
    from test_evidence_discovery_stage import _freeze_development

    from prediction_lab.evidence_discovery_stage import run_gdelt_discovery_stage

    csv, manifest = _freeze_development(tmp_path)

    class Empty:
        def search(self, *args, **kwargs):
            return []

    output = tmp_path / "discovery"
    kwargs = {
        "development_csv": csv,
        "development_manifest": manifest,
        "output_directory": output,
        "discovery": Empty(),
        "pilot_size": 3,
    }
    run_gdelt_discovery_stage(**kwargs)
    from prediction_lab.commoncrawl_evidence import HistoricalEvidenceError

    with pytest.raises(HistoricalEvidenceError, match="acquisition context"):
        run_gdelt_discovery_stage(**kwargs, lookback_days=44)
    checkpoints = list((output / "checkpoints").glob("*.json"))
    for path in checkpoints:
        payload = json.loads(path.read_text())
        payload.pop("acquisition_context_hash")
        path.write_text(json.dumps(payload))
    before = {path: path.read_bytes() for path in checkpoints}
    run_gdelt_discovery_stage(**kwargs)
    assert all(
        json.loads(line)["acquisition_state"] == "unknown_incomplete"
        for line in (output / "discovery.jsonl").read_text().splitlines()
    )
    assert before == {path: path.read_bytes() for path in checkpoints}
