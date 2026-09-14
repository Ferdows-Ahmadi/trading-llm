# Trading LLM

AI-assisted trading research platform focused on explainability, reproducibility, strategy evaluation, and eventually safe automation.

> Informational and research use only. This project does not provide guaranteed outcomes and does not authorize live trading by default.

## Project principle

> **Prove information -> prove tradability -> prove execution -> risk tiny money -> scale evidence, not confidence.**

## Research lanes

The repository currently has two distinct research lanes that share a long-term autonomous-trading goal but must remain scientifically separate.

### Prediction Market Lab

Tests whether an intelligence/forecasting layer can add information beyond a strong prediction-market baseline.

Its active experiment lives on a separate research branch with frozen scientific boundaries. Do not alter or inspect its protected artifacts casually from Market Strategy Lab work.

### Market Strategy Lab

Tests concrete trading strategies on financial markets.

Current strategy:

**Strategy 001 — ACD Fast Scalp v0.1**

Current Market Strategy Lab phase:

```text
formalization -> deterministic session/OR engine -> replay -> backtest
```

Current integration branch:

```text
research/market-strategy-lab-v0.1
```

Start here if you are contributing:

- `docs/COLLABORATOR_ONBOARDING.md`
- `docs/market-strategy-lab/README.md`
- `docs/market-strategy-lab/ACD_FAST_SCALP_V0.1.md`
- `docs/market-strategy-lab/UNRESOLVED_RULES.md`
- `docs/market-strategy-lab/EXPERIMENT_PLAN.md`

## Repository Tree

```text
.
├─ apps
│  ├─ api
│  └─ web
├─ packages
│  ├─ analytics
│  ├─ backtest
│  ├─ config
│  ├─ data-connectors
│  ├─ strategy-lab
│  ├─ scoring
│  ├─ shared
│  ├─ types
│  └─ ui
├─ db
├─ docs
└─ infra
```

`packages/strategy-lab` contains strategy-specific research logic. Generic historical replay/backtesting capability should remain reusable rather than becoming ACD-specific.

## Quick Start

1. Copy `.env.example` values into local env as needed.
2. Start the application stack:

```bash
docker compose up --build
```

3. Open:

- Web: `http://localhost:3000`
- API docs: `http://localhost:8000/api/v1/docs`

## Market Strategy Lab development

```bash
python -m pip install -e "packages/strategy-lab[dev]"
pytest packages/strategy-lab/tests -q
ruff check packages/strategy-lab
mypy packages/strategy-lab/src
```

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

## Existing platform documentation

See:

- `docs/implementation-plan.md`
- `docs/architecture.md`
- `docs/database-schema.md`
- `docs/risks.md`
- `docs/market-data-layer.md`
- `docs/analysis-engine.md`
- `docs/news-context-engine.md`
- `docs/trade-idea-generation.md`
