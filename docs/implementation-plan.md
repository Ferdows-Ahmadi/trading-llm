# Implementation Plan (Phased)

## Phase 1: Foundation Scaffold (current)
- Monorepo structure for apps, packages, infra, docs, and tests.
- FastAPI app skeleton with versioned routes and health endpoint.
- Next.js app skeleton with dashboard placeholder and API connectivity stub.
- PostgreSQL schema migrations + demo seed data.
- Docker compose for local stack.
- Base docs for architecture, schema, dependencies, and risks.

## Phase 2: Market Data Hub
- Provider adapter interfaces and concrete CCXT + Alpha Vantage adapters.
- Asset registry sync and symbol normalization workflows.
- OHLCV/snapshot ingestion jobs with retries, rate limiting, caching, quality checks.
- Provider status monitoring and health endpoints.

## Phase 3: Analysis Engine + Screeners
- Indicator computation service (EMA/SMA/RSI/MACD/ATR/Bollinger/ADX).
- Market structure and trend/regime classifiers.
- Rules-based setup detection and weighted opportunity ranking.
- API and UI pages for screeners and signal history.

## Phase 4: News and Context Engine
- News ingestion and deduplication.
- Asset relevance tagging + sentiment/importance scoring.
- Contradiction detection between price action and news flow.
- UI for News & Context page and asset-level news panels.

## Phase 5: Trade Thesis + Risk Tools
- Explainable thesis generation from deterministic factors.
- Confidence, assumptions, and contradictory factor contracts.
- Position sizing, risk/reward, exposure, and correlation risk widgets.

## Phase 6: Research Lab + Paper Trading
- Strategy builder and backtest execution pipeline (DuckDB datasets).
- Parameter search starter.
- Paper accounts/orders/fills with simulated portfolio tracking.
- Journal integration for post-trade review loop.

## Phase 7: Hardening
- Expanded test coverage (unit + integration + E2E smoke).
- CI pipeline, observability, and production deployment docs.
- Security pass (auth hardening, secret flow, role checks, rate limits).
