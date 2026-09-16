# Prospective Live Multimodel v0.2 — Stage Exit

Experiment ID: `prospective-live-multimodel-v0.2`

This document records the frozen local custody anchors for the completed prospective multimodel v0.2 experiment. The cohort, acquisition artifacts, and forecasts are closed to rerun, repair, replacement, evidence refresh, or forecast modification.

## Frozen execution state

- Selected markets: 12 from 12 distinct events.
- Forecast-ready acquisition rows: 11.
- Acquisition failure rows: 1 (`market_binding_failure`, spread above maximum).
- Acquisition operational success: true (floor: 10).
- Frozen local models:
  - `llama3.1:8b` — `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`
  - `qwen3.5:9b` — `sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`
  - `deepseek-r1:8b` — `sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763`
- All three models produced terminal forecasts for all 11 forecast-ready rows.
- Forecast operational success: true.
- Outcomes accessed: false.
- Reserved holdout accessed: false.
- Article-enrichment attempts: 27.
- Article-enrichment successes: 0. RSS fallback preserved the acquisition lane.

## Code and protocol

- Protocol commit: `b715ed5a461607c191e17ed3e1c49eb12794de30`
- Execution code commit: `be78c61d46137abe96da8652088d8761b47fe9ee`
- Frozen model manifest SHA-256: `296c91cbd22cd3d81b978f0c0a7499af8a54e9ecd8d76d20b8e6f2571691d40a`

## Local custody hashes

- `selection/selection-manifest.json`
  - SHA-256: `984752689ADA9D1006776453146ABF4274EF406E849EB9170EFB7324A979BE8A`
- `acquisition/acquisition-summary.json`
  - SHA-256: `12639F2CBCD8DC7173E6F3F1ED4BEF4C7628E82B012B37B89CF2CFD74A15DC84`
- `forecast/forecast-summary.json`
  - SHA-256: `06F455869052F48A2C391FE5030D933B2993EFD3242DE5592BE9706F2F95CF32`
- Frozen archive: `trading-live-multimodel-v0.2-frozen.zip`
  - SHA-256: `5F2BC419B725478A78BEDA026F9DCCCFE695D446F617DBD33F2F9F9EE7E2E90F`

The second attempted `Compress-Archive` invocation was rejected because the archive already existed. The archive was not overwritten or updated, and the subsequently reported SHA-256 remained identical to the original archive hash above.

## Closure rule

Do not rerun selection, reacquire evidence, replace the failed market, refresh market prices, rerun forecasts for this cohort, or overwrite the frozen ZIP. Scoring is deferred until the selected markets resolve. Outcome retrieval must occur only in a later scoring stage and must compare the already frozen model probabilities with the already frozen Polymarket priors.

The next development lane is a separate prospective experiment focused on evidence quality and source routing. It must use a new cohort and a new preregistered protocol rather than modifying v0.2.
