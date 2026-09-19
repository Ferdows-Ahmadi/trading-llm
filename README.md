# Trading Analyst Monorepo

AI-assisted trading research platform focused on evidence, explainability, and disciplined evaluation before automation.

> Informational/research output only. This project does not provide financial advice or guaranteed outcomes.

## Current Priority: Prediction Market Lab v0.1

The immediate project goal is **not live trading**. We are first building a leakage-safe evaluation harness that can answer whether a forecasting system actually beats contemporaneous prediction-market probabilities out of sample.

Current work lives in:

- `packages/prediction-lab` — forecast schema, leakage guards, Brier/log-loss/calibration metrics, evaluation CLI
- `docs/prediction-market-lab.md` — data contract and milestone plan
- `AGENTS.md` — research and engineering rules for Codex/other coding agents

Quick research-lab check:

```bash
cd packages/prediction-lab
pip install -e ".[dev]"
pytest
prediction-lab examples/sample_forecasts.csv
```

Live wallets, order execution, multi-agent orchestration, market making, and cross-venue arbitrage are intentionally deferred until the historical benchmark demonstrates a repeatable edge.

## Existing Repository Tree

```text
.
├─ apps
│  ├─ api
│  │  ├─ app
│  │  │  ├─ api/v1/endpoints
│  │  │  ├─ core
│  │  │  ├─ repositories
│  │  │  ├─ schemas
│  │  │  └─ services
│  │  └─ tests
│  └─ web
│     └─ app
├─ packages
│  ├─ analytics
│  ├─ backtest
│  ├─ prediction-lab
│  ├─ config
│  ├─ data-connectors
│  ├─ scoring
│  ├─ shared
│  ├─ types
│  └─ ui
├─ db
│  ├─ duckdb
│  └─ migrations
├─ docs
└─ infra
   ├─ docker
   └─ scripts
```

## Existing Full-Stack Quick Start

1. Copy `.env.example` values into local env as needed.
2. Start local stack:
   ```bash
   docker compose up --build
   ```
3. Open:
   - Web: `http://localhost:3000`
   - API docs: `http://localhost:8000/api/v1/docs`

### Web

```bash
pnpm install
pnpm dev:web
```

### API

```bash
cd apps/api
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Documentation

- `docs/prediction-market-lab.md` — current research-first plan
- `docs/implementation-plan.md` — original crypto/forex phased plan
- `docs/architecture.md`
- `docs/database-schema.md`
- `docs/risks.md`
- `docs/market-data-layer.md`
- `docs/analysis-engine.md`
- `docs/news-context-engine.md`
- `docs/trade-idea-generation.md`
