# Trading Analyst Monorepo

AI-assisted crypto and forex analysis platform focused on decision support, explainability, and research workflows.

> Informational output only. This project does not provide financial advice or guaranteed outcomes.

## Repository Tree (Phase 1)
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

## Quick Start
1. Copy `.env.example` values into local env as needed.
2. Start local stack:
   ```bash
   docker compose up --build
   ```
3. Open:
   - Web: `http://localhost:3000`
   - API docs: `http://localhost:8000/api/v1/docs`

## Local App Commands
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

## Phase plan
See:
- `docs/implementation-plan.md`
- `docs/architecture.md`
- `docs/database-schema.md`
- `docs/risks.md`
- `docs/market-data-layer.md`
- `docs/analysis-engine.md`
- `docs/news-context-engine.md`
- `docs/trade-idea-generation.md`
