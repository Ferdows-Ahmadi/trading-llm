from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.market_data.service import IngestionSummary, get_market_data_service
from app.repositories.market_data_repository import CandleRecord


class _FakeService:
    def available_providers(self) -> list[str]:
        return ["ccxt", "alpha_vantage"]

    def ingest_ohlcv(self, **kwargs):  # type: ignore[no-untyped-def]
        return IngestionSummary(
            provider_code=kwargs["provider_code"],
            normalized_symbol="BTCUSDT",
            timeframe=kwargs["timeframe"],
            fetched_count=2,
            inserted_count=2,
            updated_count=0,
            duration_ms=15,
        )

    def list_candles(self, **kwargs) -> list[CandleRecord]:  # type: ignore[no-untyped-def]
        return [
            CandleRecord(
                symbol="BTCUSDT",
                timeframe=kwargs["timeframe"],
                provider_code="ccxt",
                open_time=datetime(2025, 1, 1, tzinfo=UTC),
                close_time=datetime(2025, 1, 1, 1, tzinfo=UTC),
                open=100.0,
                high=110.0,
                low=90.0,
                close=105.0,
                volume=9.0,
            )
        ]


def test_market_data_providers_endpoint() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeService()
    client = TestClient(app)
    response = client.get("/api/v1/market-data/providers")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == ["ccxt", "alpha_vantage"]


def test_market_data_ingestion_endpoint() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeService()
    client = TestClient(app)
    response = client.post(
        "/api/v1/market-data/ingest/ohlcv",
        json={
            "provider_code": "ccxt",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "limit": 2,
            "asset_class": "crypto",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["normalized_symbol"] == "BTCUSDT"
    assert body["inserted_count"] == 2


def test_market_data_candles_endpoint() -> None:
    app.dependency_overrides[get_market_data_service] = lambda: _FakeService()
    client = TestClient(app)
    response = client.get("/api/v1/market-data/candles?symbol=BTCUSDT&timeframe=1h&limit=10")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "BTCUSDT"
    assert len(body["candles"]) == 1
