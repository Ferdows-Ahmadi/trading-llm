# Technical Risks

1. Provider free-tier limits can throttle ingestion and create stale signals.
   - Mitigation: request budgeting, aggressive caching, backoff/retry, health status tracking.

2. Cross-provider symbol inconsistencies can corrupt joins and analytics.
   - Mitigation: canonical asset registry and provider symbol mapping table.

3. Timezone and session-boundary bugs can skew candles and backtests.
   - Mitigation: all timestamps in UTC, explicit timezone conversion at presentation edge.

4. Data quality anomalies (missing bars, outliers, duplicates) can invalidate indicators.
   - Mitigation: ingestion QA checks, anomaly flags, provider fallback hierarchy.

5. Analysis complexity can push API latency too high for interactive UI.
   - Mitigation: async job execution, pre-computed indicator caches, pagination limits.

6. LLM summaries may overstate confidence or hide contradictory evidence.
   - Mitigation: deterministic scoring first, forced uncertainty/conflict sections in thesis schema.

7. Monorepo drift between Python and TypeScript contracts can cause runtime mismatches.
   - Mitigation: shared schema contracts, OpenAPI generation, CI checks for contract breakage.

8. Backtest realism gaps (slippage/fees/fills) can produce misleading results.
   - Mitigation: explicit assumptions, configurable execution models, compare against paper-trade logs.
