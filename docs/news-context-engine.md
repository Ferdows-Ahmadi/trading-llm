# News & Context Engine

## Implemented scope
- News ingestion via provider adapters (`alpha_vantage`).
- Deduplication using deterministic hash key from source/title/published hour.
- Asset relevance tagging with ticker and text matching against the asset registry.
- Sentiment labeling (provider signal + deterministic fallback lexicon).
- Importance scoring (recency, sentiment intensity, relevance, provider signal).
- Contradiction checks between sentiment and recent 24h price action.
- API endpoints and frontend News panel page.

## Backend modules
- `apps/api/app/news_context/adapters/*`
- `apps/api/app/news_context/service.py`
- `apps/api/app/news_context/{deduplication,tagging,sentiment,scoring}.py`
- `apps/api/app/repositories/news_context_repository.py`
- `apps/api/app/api/v1/endpoints/news_context.py`

## API endpoints
- `GET /api/v1/news/providers`
- `POST /api/v1/news/ingest`
- `GET /api/v1/news/feed`

## Frontend UI
- Dashboard panel: `apps/web/components/news-panel.tsx`
- Full page: `apps/web/app/news-context/page.tsx`

## Sample feed payload
See: `docs/samples/news-feed-sample.json`.
