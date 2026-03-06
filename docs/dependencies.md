# External Dependencies

## Runtime frameworks
- Frontend: `next`, `react`, `react-dom`, `tailwindcss`, `@tanstack/react-query`.
- Backend: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`.

## Data and analytics
- `pandas`, `numpy`, `scipy`, `statsmodels`, `duckdb`.
- `sqlalchemy`, `psycopg`.

## Provider integrations
- `ccxt` for crypto exchange adapters.
- Alpha Vantage via HTTP integration (`httpx`) for forex/crypto/news/status.

## Quality and tooling
- Python: `pytest`, `ruff`, `black`, `mypy`.
- Frontend: `typescript`, `eslint`, `prettier`, `vitest`, `playwright`.

## Infrastructure
- `docker`, `docker-compose`, `postgres`.

## Planned optional integrations (post-MVP)
- Redis for cache/job coordination.
- S3-compatible object storage for research artifacts.
- Paid market/news providers through adapter modules.
