# Prospective development custody v0.2 preregistration

Status: frozen before the first live market-universe query for v0.2.

This is a new development-validation cohort. It does not replace or mutate prospective-development-custody-v0.1. The v0.1 artifact from GitHub Actions run `34776146569` remains the canonical v0.1 result and is closed as inadequate for model-versus-market validation.

## Why v0.2 exists

The completed v0.1 run was diagnosed using blinded aggregate/status information only. No selected question text, market probability, outcome, model output, or reserved-holdout content was inspected.

The v0.1 aggregate result was:

- 33,010 market rows across 331 keyset pages;
- 160 structurally eligible markets;
- 52 deterministic parent-event representatives;
- 0 CLOB-valid representatives;
- 0 selected rows;
- 0 CLOB transport failures.

All 52 event representatives carried the same `invalid_clob_price` rejection code. Schema-only inspection of the frozen CLOB response objects established that all midpoint responses used a `mid` field, while the v0.1 parser accepted only `mid_price`. No midpoint numeric values were manually inspected for this diagnosis.

The current public Polymarket documentation is internally inconsistent with observed/live client behavior: the API reference documents `mid_price`, while current Polymarket market-data tooling documents a `mid` response. v0.2 therefore preregisters an explicit alias rule rather than adapting after acquisition.

Separately, v0.1 produced only 52 structurally eligible parent-event representatives in the 7-to-45-day window, below the 60-case adequacy floor even before CLOB filtering. This is a blinded recruitment-rate fact, not an outcome or model-performance result. v0.2 performs one predeclared sample-size design correction by doubling the maximum scheduled horizon from 45 to 90 days. No volume, liquidity, spread, event-independence, or contract-custody threshold is relaxed.

## Independence from v0.1

v0.2 uses a fresh live snapshot, a new selection seed, a new artifact identity, and a new snapshot timestamp. It does not reprocess v0.1 raw prices into a replacement cohort and does not substitute any v0.1 market.

Selection seed:

`prospective-development-custody-v0.2-selection-seed-2026-09-13`

Target cohort size: **100 event-independent markets**.

Adequacy floor: **60 selected cases at custody time**, followed by the existing requirement that at least 60 ultimately resolve and are independently adjudicable before any model-versus-market edge claim is permitted.

If fewer than 60 CLOB-valid event-independent cases are selected, the v0.2 custody artifact is frozen and reported as inadequate. There is no threshold relaxation, replacement, or rerun to rescue sample size.

## Snapshot reference and forecast horizon

The collector records one UTC `snapshot_reference_at` immediately before the first live market-list request.

Frozen scheduled-end window:

- minimum: `snapshot_reference_at + 7 days`;
- maximum: `snapshot_reference_at + 90 days`.

Each market/CLOB request records its own acquisition time. Every selected row has `source_cutoff_at = snapshot_reference_at`.

## Market-universe transport

Use Polymarket Gamma:

`GET https://gamma-api.polymarket.com/markets/keyset`

Frozen parameters on every page:

- `closed=false`;
- `end_date_min=<snapshot_reference_at + 7d>`;
- `end_date_max=<snapshot_reference_at + 90d>`;
- `order=id`;
- `ascending=true`;
- `limit=100`.

Pagination rules:

- omit `after_cursor` on page 0;
- if `next_cursor` is a non-empty string, replay that exact opaque value as the next page's `after_cursor`;
- stop only when `next_cursor` is absent or empty;
- reject malformed non-string cursors;
- reject repeated non-empty cursors;
- reject duplicate non-empty market IDs across pages;
- hard keyset safety ceiling: **1,000 pages**; a remaining cursor after page 1,000 is failure, not permission to truncate.

Freeze each raw Gamma response before normalized selection output is written.

No category, topic, keyword, outcome, later resolution, model result, or market-direction filter is permitted.

## Structural market eligibility

The v0.1 structural criteria are retained except for the preregistered 90-day maximum scheduled horizon. A Gamma market is structurally eligible only if:

1. non-empty `id`, `conditionId`, `question`, and `endDate`;
2. `closed` is false;
3. `active` is not explicitly false;
4. `enableOrderBook` is true;
5. `acceptingOrders` is true;
6. exactly two outcomes normalize to `Yes` and `No`;
7. exactly two CLOB token IDs map one-to-one to those outcomes;
8. a parent Polymarket event ID is derivable from embedded event metadata;
9. scheduled `endDate` is within the frozen 7-to-90-day window;
10. `volumeNum >= 5000`;
11. `liquidityNum >= 1000`;
12. non-empty market description plus at least one non-empty resolution-source locator from the market or parent event.

Unknown or malformed values fail eligibility. No discretionary repair is allowed.

## Event independence and representative selection

Group structurally eligible markets by exact parent event ID.

For each parent event, select the single representative minimizing lowercase hexadecimal SHA256 of:

`<v0.2-selection-seed>|<event-id>|<market-id>`

No second market from the event may substitute if that representative later fails CLOB validation.

## CLOB market snapshot

For the Yes token of every deterministic event representative, freeze raw responses and timestamps from:

- best bid: `GET https://clob.polymarket.com/price?token_id=<YES>&side=BUY`;
- best ask: `GET https://clob.polymarket.com/price?token_id=<YES>&side=SELL`;
- midpoint: `GET https://clob.polymarket.com/midpoint?token_id=<YES>`.

The bid and ask response must contain numeric `price` values.

The midpoint response is parsed under this frozen alias rule:

1. if exactly one of `mid` or `mid_price` is present, parse that field;
2. if both are present, both must parse as numeric and be exactly equal as decimal values; otherwise reject with `conflicting_midpoint_aliases`;
3. if neither is present, reject with `missing_midpoint_field`;
4. any nonnumeric accepted field is `invalid_clob_price`.

After parsing, bid, ask, and midpoint must each be strictly between 0 and 1. The representative passes only if:

- `bid <= midpoint <= ask`;
- `ask - bid <= 0.10`;
- all three responses were acquired successfully in the same collector run.

The canonical market baseline probability is the accepted CLOB midpoint value. Gamma probability-like fields remain noncanonical.

## Final cohort selection

CLOB-valid event representatives are ranked by lowercase hexadecimal SHA256 of:

`<v0.2-selection-seed>|<event-id>`

Select the first 100, or all if fewer than 100 pass. No later replacement is permitted.

The workflow may print only aggregate counts, hashes, acquisition status, and reason-code counts. It must not print selected question text, selected market probability, category, event title, slug, or other semantic content before the evidence/forecaster protocol is frozen.

## Immutable payload and provenance

The v0.2 artifact must freeze:

- all raw Gamma keyset pages;
- all raw CLOB responses for attempted event representatives;
- normalized universe identity/hash metadata;
- full deterministic eligibility/selection ledger and reason codes;
- selected cohort JSONL;
- acquisition receipts and hashes;
- source URLs/parameters/timestamps;
- code commit and this protocol commit;
- exact selected contract text/rules/source locators and identifiers inside the artifact, while keeping them out of workflow logs;
- CLOB bid/ask/midpoint/spread and price timestamp;
- SHA256 of each selected canonical contract object.

The first v0.2 workflow that completes the full live universe and uploads an immutable artifact is the only v0.2 cohort. A completed artifact may not be replaced by rerunning acquisition to obtain a more favorable sample.

Engineering reruns are permitted only if acquisition fails before a completed cohort artifact is produced, and only under unchanged scientific query/selection rules unless another transport-only amendment is committed before the retry.

## No model inference and no holdout access

Custody v0.2 must not invoke an LLM/forecast model, score model versus market, inspect future outcomes, or access the existing 73-case reserved holdout.

If custody is adequate, a separate evidence/forecaster protocol must be committed before selected question/probability content is manually inspected or any model forecast is produced. That later protocol must bind the model identity, leakage cutoff, evidence acquisition/freeze procedure, prompt, output schema, no-evidence behavior, probability transformation, failure accounting, paired Brier/log-loss analysis, uncertainty method, deletion sensitivity, calibration reporting, and no post-hoc category filtering or threshold tuning.

## Resolution stopping rule

Cohort membership never changes after custody. Development-validation analysis is authorized only after every selected case reaches terminal resolution/adjudication or 90 days elapse after the latest selected scheduled end time, whichever stopping condition is reached first under the later frozen resolution policy.

If fewer than 60 selected cases ultimately both resolve and are independently adjudicable, v0.2 is inadequate for a model-versus-market edge claim. Smaller samples may be reported operationally only.
