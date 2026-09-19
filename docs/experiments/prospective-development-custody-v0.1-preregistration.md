# Prospective development custody v0.1 preregistration

Status: preregistered before the first live market-universe query for this cohort.

This stage exists because the historical-validity audit v1 produced only three defensible historical cases. The failure mode was historical contract custody, not candidate resolution. This protocol therefore creates contract custody prospectively at forecast time instead of reconstructing it later.

This is a **development-validation** cohort. It does not open, inspect, score, or otherwise consume the existing reserved holdout. It also does not authorize a model forecast yet. Market/contract custody is frozen first; evidence and forecaster rules are frozen separately before any model inference on this cohort.

## One-time cohort

The cohort is a single immutable snapshot, not an adaptive rolling sample.

The first successful acquisition workflow launched after this protocol is committed is the only authorized live universe query for `prospective-development-custody-v0.1`. If acquisition fails before any live market response is persisted, an engineering-only rerun is permitted with unchanged query/selection rules. If a complete live universe response is obtained and the cohort is frozen, no later market may be added, substituted, or replaced under this protocol.

Selection seed:

`prospective-development-custody-v0.1-selection-seed-2026-09-13`

Target cohort size: **100 event-independent markets**.

Adequacy floor: **60 eventually resolved, adjudicable event-independent cases**. If fewer than 60 structurally eligible event representatives exist in the one-time snapshot, the custody artifact is still frozen and reported, but no model-versus-market validation is authorized from this cohort. No threshold is relaxed to rescue sample size.

## Snapshot reference time and forecast horizon

At acquisition start, the collector records one UTC `snapshot_reference_at` before making the market-list request.

The eligible scheduled-end window is computed from that fixed timestamp:

- minimum scheduled horizon: `snapshot_reference_at + 7 days`;
- maximum scheduled horizon: `snapshot_reference_at + 45 days`.

This replaces the retrospective `actual closedTime - 7d` rule. The horizon is prospectively executable and does not depend on future closure information.

All market and price requests record their individual acquisition timestamps. `snapshot_reference_at` is the cohort timing anchor; the exact CLOB price request timestamp is the market-price timestamp.

## Frozen market-universe query

Source: Polymarket public Gamma API `GET https://gamma-api.polymarket.com/markets`.

The collector pages with:

- `closed=false`;
- `end_date_min=<snapshot_reference_at + 7d>`;
- `end_date_max=<snapshot_reference_at + 45d>`;
- `order=id`;
- `ascending=true`;
- `limit=100`;
- deterministic `offset=0,100,200,...` pagination until a page contains fewer than 100 rows;
- hard safety limit: 100 pages. Hitting the safety limit is acquisition failure, not permission to truncate silently.

The exact JSON response from every Gamma page is frozen before normalized selection output is written.

No category, topic, keyword, outcome, later resolution, model result, or market-direction filter is permitted.

## Structural market eligibility

A Gamma market is structurally eligible only if all conditions below hold at acquisition:

1. non-empty `id`, `conditionId`, `question`, and `endDate`;
2. `closed` is false;
3. `active` is not explicitly false;
4. `enableOrderBook` is true;
5. `acceptingOrders` is true;
6. exactly two outcomes normalize to `Yes` and `No`;
7. exactly two CLOB token IDs are present and map one-to-one to the two outcomes;
8. a parent Polymarket event ID can be derived from embedded event metadata; fallback market-level grouping is not accepted for this prospective cohort;
9. the scheduled `endDate` lies inside the frozen 7-to-45-day window;
10. `volumeNum >= 5000` USD-equivalent units as reported by Gamma;
11. `liquidityNum >= 1000` USD-equivalent units as reported by Gamma;
12. historical contract custody is possible: non-empty market `description` and at least one non-empty resolution-source locator from the market or embedded parent event.

Unknown/malformed values fail eligibility. There is no discretionary repair or alternate market substitution.

## Event independence and representative selection

All structurally eligible markets are grouped by exact Polymarket parent event ID.

Within each parent event, the single representative is the market minimizing the lowercase hexadecimal SHA256 of:

`<selection-seed>|<event-id>|<market-id>`

This choice is independent of market probability, outcome, category, model behavior, and later resolution.

No second market from the same parent event may enter the cohort even if the chosen representative later fails its CLOB snapshot check.

## Live market-probability snapshot

For each deterministic event representative, the collector queries the Polymarket CLOB for the **Yes** token only and freezes the raw responses plus request timestamps.

Required price observations:

- best bid from `GET https://clob.polymarket.com/price?token_id=<YES>&side=BUY`;
- best ask from `GET https://clob.polymarket.com/price?token_id=<YES>&side=SELL`;
- midpoint from `GET https://clob.polymarket.com/midpoint?token_id=<YES>`.

A representative passes the CLOB snapshot check only when:

- bid, ask, and midpoint are numeric and strictly between 0 and 1;
- `bid <= midpoint <= ask`;
- `ask - bid <= 0.10`;
- all three responses are acquired successfully in the same collector run.

The frozen baseline market probability is the CLOB midpoint returned by the public midpoint endpoint. Gamma `outcomePrices`, `bestBid`, `bestAsk`, and `lastTradePrice` are frozen as part of raw custody but are not used as the canonical baseline probability.

CLOB snapshot failure excludes that event representative. Another market from the same event is not substituted.

## Final cohort selection

CLOB-valid event representatives are ranked by lowercase hexadecimal SHA256 of:

`<selection-seed>|<event-id>`

The first 100 representatives are selected. If fewer than 100 pass, all passing representatives are selected. No replacement occurs later.

The workflow summary may print counts, hashes, and acquisition status only. It must not print selected question text or probabilities. Manual inspection of selected question/probability content is deferred until the evidence/forecaster protocol is frozen.

## Frozen custody payload

The immutable artifact must contain at least:

- raw Gamma page responses;
- normalized full-universe identity/hash metadata;
- a complete deterministic eligibility/selection ledger including rejected representatives and reason codes;
- raw CLOB bid/ask/midpoint responses for every event representative that reached price acquisition;
- selected cohort CSV/JSONL;
- acquisition manifest and hashes;
- source URLs, request parameters, request timestamps, and code commit;
- exact question text;
- exact market description/rules;
- market and parent-event IDs/slugs;
- market and event resolution-source locators;
- condition ID and Yes/No token IDs;
- scheduled end time;
- category;
- reported volume/liquidity;
- exact canonical midpoint, bid, ask, spread, and price timestamp;
- SHA256 of a canonical contract object containing question, description/rules, resolution-source locator(s), IDs/slugs, outcomes/token IDs, and scheduled end time.

All selected rows have `source_cutoff_at = snapshot_reference_at`. Later evidence supplied to a forecaster must satisfy a separately preregistered evidence-cutoff rule at or before this timestamp.

## No model inference in custody stage

This workflow must not invoke any LLM or forecasting model, construct residual actions, calculate model-versus-market scores, inspect outcomes, or resolve any selected case.

After the cohort is frozen, a separate protocol must bind the exact model identity, model cutoff/leakage-safety rule, evidence acquisition/freeze procedure, prompt, output schema, no-evidence behavior, probability transformation, failure accounting, and paired statistical analysis **before any model forecast is produced for these selected cases**.

## Resolution and analysis stopping rule

The cohort membership never changes after custody.

Resolution review occurs after cases naturally resolve. The final development-validation analysis is authorized only after either:

1. every selected case has reached a terminal resolution/adjudication state; or
2. 90 days have elapsed after the latest scheduled `endDate` among selected cases.

All selected cases remain in accounting. Cancelled, ambiguous, unresolved, or unverifiable cases are reported under a separately preregistered resolution policy and are never replaced.

If fewer than 60 cases are ultimately both resolved and independently adjudicable, the cohort is declared inadequate for a model-versus-market edge claim. A smaller sample may be described operationally but may not be promoted as confirmatory evidence.

## Planned analysis constraints

Before forecasts are produced, the analysis protocol must preregister at least:

- paired Brier-score difference versus the frozen market midpoint;
- paired log-loss difference versus the frozen market midpoint;
- event-level uncertainty intervals/resampling;
- sensitivity to individual-case deletion and concentration of improvement;
- explicit failure denominator;
- label balance and calibration reporting;
- a no-single-case-domination diagnostic;
- no post-hoc category filtering or threshold tuning.

## Holdout status

The existing reserved holdout remains reserved from adaptive forecaster evaluation. Nothing in this prospective development-custody protocol authorizes access to it.
