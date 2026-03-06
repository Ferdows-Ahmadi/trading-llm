# Backend Market Data Layer

## Scope
- Provider adapter abstraction for OHLCV.
- CCXT and Alpha Vantage adapters.
- Symbol normalization across crypto and forex.
- Ingestion and retrieval API endpoints.
- Historical candle storage through repository + ORM models.
- Shared resilience policies: caching, retries, and rate limiting.

## Module layout (`apps/api/app`)
- `market_data/domain.py`: canonical request/candle DTOs.
- `market_data/normalization.py`: symbol normalization and provider formatting.
- `market_data/adapters/*`: provider implementations and registry.
- `market_data/resilience/*`: cache/retry/rate-limit primitives.
- `market_data/service.py`: ingestion orchestration.
- `repositories/market_data_repository.py`: persistence operations.
- `models/market_data.py`: storage models (`providers`, `assets`, `asset_provider_symbols`, `candles`, `ingestion_runs`).
- `api/v1/endpoints/market_data.py`: API endpoints.

## API endpoints
- `GET /api/v1/market-data/providers`
- `POST /api/v1/market-data/ingest/ohlcv`
- `GET /api/v1/market-data/candles`

## Resilience behavior
- Cache: in-memory TTL cache keyed by provider + symbol + timeframe + limit + since.
- Retry: exponential backoff (`MARKET_DATA_RETRY_ATTEMPTS`, `MARKET_DATA_RETRY_BACKOFF_SECONDS`).
- Rate limiting: per-provider sliding window (default CCXT=60/min, Alpha Vantage=5/min).

## Notes
- Alpha Vantage crypto support is implemented for `1d` timeframe currently.
- Alpha Vantage adapter is enabled only when `ALPHAVANTAGE_API_KEY` is configured.
