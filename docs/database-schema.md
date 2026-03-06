# Database Schema (PostgreSQL + DuckDB)

## PostgreSQL purpose
- Operational data store for users, assets, provider metadata, market snapshots, signals, theses, alerts, paper trading, and journal records.

## DuckDB purpose
- Analytics sandbox for backtest datasets, parameter sweeps, and large time-series research joins.

## Core relational tables
- `users`, `user_settings`
- `providers`, `provider_health_events`, `ingestion_runs`
- `assets`, `asset_provider_symbols`
- `candles`, `snapshots`, `indicator_values`
- `news_items`, `news_asset_links`
- `opportunities`, `theses`, `alerts`
- `watchlists`, `watchlist_assets`
- `journal_entries`
- `backtest_runs`, `backtest_results`
- `paper_accounts`, `paper_orders`, `paper_fills`

## Design notes
- UUID primary keys for distributed-safe writes.
- UTC-safe timestamps (`TIMESTAMPTZ`) across all time-aware tables.
- JSONB for extensible payloads (score breakdowns, metadata, settings).
- Uniqueness constraints for de-duplication:
  - `assets.normalized_symbol`
  - `candles(asset_id, provider_id, timeframe, open_time)`
  - `indicator_values(asset_id, timeframe, observed_at, indicator_key)`
  - `news_asset_links(news_item_id, asset_id)`

## Initial migration files
- `db/migrations/0001_init.sql`: schema and indexes.
- `db/migrations/0002_seed_base_data.sql`: base providers and example assets.
