import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from prediction_lab import prospective_polymarket_custody as custody
from prediction_lab.prospective_live_rss_v01 import GoogleNewsRssClient
from prediction_lab.prospective_live_session_v01 import (
    MODEL_DIGEST,
    MODEL_TAG,
    PROTOCOL_COMMIT,
    SessionError,
    run_acquisition,
    verify_ollama_model,
)

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss><channel><item><title>Live update</title>
<link>https://example.com/live</link><description>Current context</description>
<source>Example</source></item></channel></rss>
"""


class FakeClobClient:
    def _response(self, payload: object, kind: str) -> custody.FrozenResponse:
        acquired_at = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
        raw = json.dumps(payload).encode("utf-8")
        return custody.FrozenResponse(
            payload=payload,
            raw=raw,
            acquired_at=acquired_at,
            url=f"https://clob.example/{kind}",
            params={},
        )

    def clob_price(self, token_id: str, side: str) -> custody.FrozenResponse:
        price = "0.49" if side == "BUY" else "0.51"
        return self._response({"price": price}, f"{token_id}-{side}")

    def clob_midpoint(self, token_id: str) -> custody.FrozenResponse:
        return self._response({"mid": "0.50"}, f"{token_id}-mid")


def _write_selection(root: Path) -> tuple[Path, Path]:
    selected = root / "selected-candidates.jsonl"
    manifest = root / "selection-manifest.json"
    snapshot = datetime.now(UTC) - timedelta(minutes=1)
    rows = []
    for index in range(8):
        rows.append(
            {
                "market_id": f"m{index}",
                "condition_id": f"c{index}",
                "event_id": f"e{index}",
                "market_slug": f"market-{index}",
                "event_slug": f"event-{index}",
                "question_text": f"Will event {index} happen?",
                "description": "Resolves Yes if the event occurs.",
                "resolution_sources": ["https://example.com/rules"],
                "yes_token_id": f"yes-{index}",
                "no_token_id": f"no-{index}",
                "scheduled_end_at": (snapshot + timedelta(days=10)).isoformat(),
                "category": "test",
                "volume_num": 10000.0,
                "liquidity_num": 5000.0,
                "selection_snapshot_at": snapshot.isoformat(),
                "event_candidate_rank": f"rank-{index}",
                "pilot_rank": f"pilot-{index}",
            }
        )
    selected.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "purpose": "prospective-live-capture-pilot-v0.1",
                "protocol_commit": PROTOCOL_COMMIT,
                "selected_rows": 8,
                "snapshot_reference_at": snapshot.isoformat(),
                "evidence_accessed": False,
                "outcomes_accessed": False,
                "reserved_holdout_accessed": False,
            }
        ),
        encoding="utf-8",
    )
    return selected, manifest


def test_acquisition_freezes_evidence_then_valid_market_snapshot(tmp_path: Path) -> None:
    selection_root = tmp_path / "selection"
    selection_root.mkdir()
    selected, manifest = _write_selection(selection_root)

    def rss_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RSS, request=request)

    rss_client = GoogleNewsRssClient(
        client=httpx.Client(transport=httpx.MockTransport(rss_handler)),
        retries=1,
        retry_backoff_seconds=0,
    )
    output = tmp_path / "acquisition"
    summary = run_acquisition(
        selected_candidates_path=selected,
        selection_manifest_path=manifest,
        output_directory=output,
        code_commit="test-commit",
        rss_client=rss_client,
        market_client=FakeClobClient(),
    )
    assert summary["selected_rows"] == 8
    assert summary["forecast_ready_rows"] == 8
    assert summary["status_counts"] == {"forecast_ready": 8}
    assert summary["model_forecast_run"] is False
    assert summary["outcomes_accessed"] is False
    assert summary["reserved_holdout_accessed"] is False
    assert len(list((output / "rows").glob("*/bound-row.json"))) == 8
    assert len(list((output / "rows").glob("*/evidence-packet.json"))) == 8


def test_selection_window_failure_does_not_query_rss(tmp_path: Path) -> None:
    selection_root = tmp_path / "selection"
    selection_root.mkdir()
    selected, manifest = _write_selection(selection_root)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["snapshot_reference_at"] = "2026-01-01T00:00:00Z"
    manifest.write_text(json.dumps(value), encoding="utf-8")

    calls = 0

    def rss_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=RSS, request=request)

    rss_client = GoogleNewsRssClient(
        client=httpx.Client(transport=httpx.MockTransport(rss_handler)),
        retries=1,
        retry_backoff_seconds=0,
    )
    summary = run_acquisition(
        selected_candidates_path=selected,
        selection_manifest_path=manifest,
        output_directory=tmp_path / "acquisition",
        code_commit="test-commit",
        rss_client=rss_client,
        market_client=FakeClobClient(),
        now=lambda: datetime(2026, 1, 1, 3, 0, tzinfo=UTC),
    )
    assert summary["forecast_ready_rows"] == 0
    assert summary["status_counts"] == {"selection_window_failure": 8}
    assert calls == 0


def test_verify_ollama_model_requires_exact_digest(tmp_path: Path) -> None:
    expected = MODEL_DIGEST.removeprefix("sha256:")

    def good_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"models": [{"name": MODEL_TAG, "digest": expected}]},
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(good_handler))
    receipt = verify_ollama_model(
        base_url="http://ollama.test",
        output_directory=tmp_path / "good",
        client=client,
    )
    assert receipt["verified"] is True
    assert receipt["model_digest"] == MODEL_DIGEST

    def bad_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"models": [{"name": MODEL_TAG, "digest": "bad"}]},
            request=request,
        )

    bad_client = httpx.Client(transport=httpx.MockTransport(bad_handler))
    with pytest.raises(SessionError):
        verify_ollama_model(
            base_url="http://ollama.test",
            output_directory=tmp_path / "bad",
            client=bad_client,
        )
