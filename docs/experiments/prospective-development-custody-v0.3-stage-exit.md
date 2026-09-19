# Prospective clustered development custody v0.3 stage exit

Status: completed successfully. The frozen authorization gates permit an exploratory development forecaster stage, but do not authorize a confirmatory model-versus-market edge claim.

Canonical custody protocol commit: `a4de3487a3c931b9e04578b7a501aabb6050e0cc`.

Canonical acquisition workflow commit: `5bf128ebddb1fe82f578072beb2028545c824553`.

Canonical GitHub Actions run: `34777066496`.

Canonical artifact: `prospective-development-custody-v0.3`, artifact ID `10323747083`, uploaded ZIP SHA256 `01eebf244add1ff21ee8d21257a000c5ee9588f751ae456e7fc7d17c0704a6aa`.

## Completed custody result

The run completed the frozen pre-live contract checks, full Gamma keyset acquisition, CLOB acquisition, deterministic clustered selection accounting, and immutable artifact upload.

Aggregate result:

- snapshot reference: `2026-09-13T19:14:39.226442Z`;
- Gamma keyset pages: 431;
- universe rows: 43,068;
- structurally eligible markets: 164;
- structurally eligible parent-event groups: 55;
- deterministic event candidates under the two-per-event cap: 82 across 55 event groups;
- CLOB-valid candidates: 77;
- CLOB transport failures: 0;
- rejected candidates: 5, comprising 4 `invalid_clob_price` and 1 `spread_above_maximum`;
- selected rows: 77;
- selected parent-event groups: 53;
- selected within-event ranks: 52 rank-1 and 25 rank-2 markets;
- selected cluster sizes: 29 one-market events and 24 two-market events;
- development forecaster authorized: **true**;
- confirmatory edge claim authorized: **false**;
- cohort SHA256: `6c3cea364fd7548934a5e0e3e5a00cb45d1dd124318d9cf31ea0c012af661634`;
- selection-ledger SHA256: `f9f3377372003602158e3bc0785ae34be3ce119119fbfe942b53940f51366ff6`;
- universe SHA256: `a3f5baf6494df4ce3dad0673cc8466290150f980fb435cf36a93ff8eb9cd948c`.

The preregistered authorization floors were at least 60 selected CLOB-valid markets and at least 40 distinct parent-event clusters. The canonical cohort contains 77 markets across 53 clusters, so both floors pass without any post-acquisition threshold change.

## Blinding state at stage exit

Before this stage-exit record and the separate forecaster/evidence preregistration were committed, review was restricted to workflow status, aggregate counts, hashes, reason-code counts, artifact identity, and anonymous cluster accounting.

Selected question text, description/rules, category, slug, market probability, bid/ask/midpoint values, resolution outcome, and model output were not manually inspected. The reserved 73-case holdout was not opened or accessed.

## Authorization boundary

The successful custody run authorizes only a separately preregistered exploratory development forecaster on the 77 frozen rows. It does not authorize:

- scoring against outcomes before the frozen prospective resolution stopping rule is reached;
- treating 77 rows as 77 independent observations;
- a confirmatory claim that the model beats the market;
- prompt/model/evidence tuning after observing v0.3 outcomes;
- opening the reserved 73-case holdout.

Before selected semantic content is manually inspected or any model forecast is generated, the next protocol must freeze exact model identity, timestamp-safe evidence acquisition, prompt/output contract, no-evidence/failure handling, residual mapping, clustered estimand, cluster-resampled uncertainty, sensitivity analysis, and future resolution/scoring rules.
