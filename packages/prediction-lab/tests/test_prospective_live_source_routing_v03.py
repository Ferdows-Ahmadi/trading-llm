from __future__ import annotations

from datetime import UTC, datetime

import pytest

from prediction_lab import prospective_live_source_routing_session_v03 as session
from prediction_lab import prospective_live_source_routing_v03 as selector


def _eligible(market_id: int, event_id: int) -> dict[str, object]:
    return {"market_id": str(market_id), "event_id": str(event_id)}


def test_v03_selector_identity_and_event_uniqueness_are_frozen() -> None:
    assert selector.PROTOCOL_COMMIT == "6581cffba826c61548fba00eaf68d6ef57340dbe"
    assert selector.MODEL_MANIFEST_SHA256 == (
        "440d3623c08082b724e5685975fdb1062a68e9796d9fbe1e20fabf5422667310"
    )
    assert selector.TARGET_COHORT == 12
    rows = [_eligible(index, index // 2) for index in range(40)]
    first = selector.select_structural_candidates(rows)  # type: ignore[arg-type]
    second = selector.select_structural_candidates(list(reversed(rows)))  # type: ignore[arg-type]
    assert first == second
    assert len(first) == 12
    assert len({str(row["event_id"]) for row in first}) == 12


def test_v03_exact_model_identities_are_bound_to_preselection_freeze() -> None:
    assert selector.FROZEN_MODELS == (
        (
            "llama3.1:8b",
            "sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e",
        ),
        (
            "qwen3.5:9b",
            "sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7",
        ),
        (
            "deepseek-r1:8b",
            "sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763",
        ),
    )
    assert session.FROZEN_MODELS == selector.FROZEN_MODELS
    assert session.CONDITIONS == ("condition-a", "condition-b")
    assert session.ACQUISITION_SUCCESS_FLOOR == 10


class _DummyAdapter:
    def __init__(self, **_: object) -> None:
        pass

    def close(self) -> None:
        pass


def test_paired_forecast_accounting_is_six_cells_and_preserves_failures(
    tmp_path, monkeypatch
) -> None:
    acquisition = tmp_path / "acquisition"
    rows_root = acquisition / "rows"
    records: list[dict[str, object]] = []
    timestamp = datetime(2026, 9, 18, 17, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z")

    for index in range(12):
        market_id = str(1000 + index)
        event_id = str(2000 + index)
        ready = index < 10
        record: dict[str, object] = {
            "market_id": market_id,
            "event_id": event_id,
            "question_id": f"polymarket-market:{market_id}",
            "status": "forecast_ready" if ready else "market_binding_failure",
            "forecast_ready": ready,
        }
        records.append(record)
        if not ready:
            continue

        row_directory = rows_root / session.v01._safe_market_id(market_id)
        row = {
            "market_id": market_id,
            "event_id": event_id,
            "within_event_rank": 1,
            "market_probability": 0.5,
            "market_price_timestamp": timestamp,
            "source_cutoff_at": timestamp,
        }
        packet_a = session._packet(
            question_id=f"polymarket-market:{market_id}",
            status="verified_empty",
            raw_items=[],
            capture_completed_at=timestamp,
            market_price_timestamp=timestamp,
            condition="Condition A",
        )
        packet_b = session._packet(
            question_id=f"polymarket-market:{market_id}",
            status="verified_empty",
            raw_items=[],
            capture_completed_at=timestamp,
            market_price_timestamp=timestamp,
            condition="Condition B",
        )
        session._atomic_json(row_directory / "bound-row.json", row)
        session._atomic_json(row_directory / "condition-a-packet.json", packet_a.to_dict())
        session._atomic_json(row_directory / "condition-b-packet.json", packet_b.to_dict())

    summary = {
        "schema_version": 1,
        "experiment_id": session.EXPERIMENT_ID,
        "protocol_commit": session.PROTOCOL_COMMIT,
        "preselection_model_manifest_sha256": session.MODEL_MANIFEST_SHA256,
        "forecast_ready_rows": 10,
        "records": records,
        "outcomes_accessed": False,
        "reserved_holdout_accessed": False,
    }
    acquisition.mkdir(parents=True, exist_ok=True)
    session._atomic_json(acquisition / "acquisition-summary.json", summary)

    monkeypatch.setattr(session, "OllamaMarketResidualV2Adapter", _DummyAdapter)
    monkeypatch.setattr(
        session,
        "verify_model_set",
        lambda **_: {
            "verified": True,
            "models": [
                {"tag": tag, "digest": digest} for tag, digest in session.FROZEN_MODELS
            ],
        },
    )

    result = session.run_forecasting(
        acquisition_directory=acquisition,
        output_directory=tmp_path / "forecast",
        code_commit="test-commit",
    )
    assert result["operational_success"] is True
    cells = result["cells"]
    assert isinstance(cells, dict)
    assert len(cells) == 6
    assert all(value["terminal_forecast_rows"] == 10 for value in cells.values())
    assert all(value["operational_success"] is True for value in cells.values())
    forecast_records = result["records"]
    assert isinstance(forecast_records, list)
    assert len(forecast_records) == 72
    assert sum(
        record["status"] == "acquisition_failure_no_forecast"
        for record in forecast_records
    ) == 12

    with pytest.raises(session.SourceRoutingSessionError, match="Refusing to replace"):
        session.run_forecasting(
            acquisition_directory=acquisition,
            output_directory=tmp_path / "forecast",
            code_commit="test-commit",
        )
