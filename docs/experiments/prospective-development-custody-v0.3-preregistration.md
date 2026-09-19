# Prospective clustered development custody v0.3 preregistration

Status: frozen before the first live market-universe query for v0.3.

This stage is an **exploratory model-development cohort**. It is not a confirmatory edge test and must not be described as one, regardless of eventual model performance or nominal p-values.

The reason for v0.3 is a blinded recruitment limitation observed in completed prospective custody v0.2: 161 structurally eligible markets were concentrated into only 52 anonymous parent events, producing 48 CLOB-valid event-independent cases versus the frozen 60-case adequacy floor. No question text, category/topic, selected probability, outcome, or model result was inspected in making this design change.

v0.3 deliberately permits limited within-event clustering so that forecaster engineering can proceed without weakening market-quality or contract-custody thresholds. The existing reserved 73-case holdout remains untouched and is reserved for later independent evaluation.

## Cohort identity and stopping rule

v0.3 is a fresh live snapshot. It does not reuse or reselect rows from v0.1 or v0.2.

Selection seed:

`prospective-development-custody-v0.3-selection-seed-2026-09-13`

Target cohort size: **80 markets**.

Per-parent-event cap: **2 markets**.

Development-forecaster authorization floor:

- at least **60 CLOB-valid selected markets**; and
- at least **40 distinct parent-event clusters** among selected markets.

These thresholds authorize exploratory forecaster development only. They do not authorize a confirmatory model-versus-market edge claim.

If either floor is missed, the completed artifact is frozen and v0.3 forecaster execution is not authorized. No thresholds may be relaxed after acquisition to rescue sample size.

The first v0.3 workflow that completes the full live universe and uploads an immutable artifact is the only v0.3 cohort. A completed artifact may not be rerun or replaced to obtain more favorable membership.

## Snapshot reference and horizon

Record one UTC `snapshot_reference_at` immediately before the first live market-list request.

Frozen scheduled-end window:

- minimum: `snapshot_reference_at + 7 days`;
- maximum: `snapshot_reference_at + 90 days`.

The 90-day window is retained from v0.2 so the only material recruitment change in v0.3 is the explicitly declared within-event cap.

Every selected row receives `source_cutoff_at = snapshot_reference_at`. Each CLOB request records its own acquisition timestamp.

## Gamma universe transport

Use:

`GET https://gamma-api.polymarket.com/markets/keyset`

Frozen parameters:

- `closed=false`;
- `end_date_min=<snapshot_reference_at + 7d>`;
- `end_date_max=<snapshot_reference_at + 90d>`;
- `order=id`;
- `ascending=true`;
- `limit=100`.

Pagination:

- omit `after_cursor` on page 0;
- replay each exact non-empty opaque `next_cursor` as the next page's `after_cursor`;
- terminate only when `next_cursor` is absent or empty;
- reject malformed non-string cursors;
- reject repeated non-empty cursors;
- reject duplicate non-empty market IDs across pages;
- hard safety ceiling 1,000 pages; a remaining cursor after page 1,000 is acquisition failure, not truncation permission.

Freeze each raw Gamma response before normalized selection output is written.

No topic, category, keyword, direction, later outcome, model result, or semantic-content filter is permitted.

## Structural market eligibility

Retain the v0.2 structural criteria unchanged. A market is structurally eligible only if all of the following hold at acquisition:

1. non-empty `id`, `conditionId`, `question`, and `endDate`;
2. `closed` is false;
3. `active` is not explicitly false;
4. `enableOrderBook` is true;
5. `acceptingOrders` is true;
6. exactly two outcomes normalize to `Yes` and `No`;
7. exactly two CLOB token IDs map one-to-one to the outcomes;
8. an exact parent Polymarket event ID is derivable from embedded event metadata;
9. scheduled `endDate` lies inside the frozen 7-to-90-day window;
10. `volumeNum >= 5000`;
11. `liquidityNum >= 1000`;
12. non-empty market description and at least one non-empty resolution-source locator from the market or embedded parent event.

Unknown or malformed values fail eligibility. No discretionary repair is allowed.

## Deterministic clustered representative selection

Group structurally eligible markets by exact parent event ID.

Within each event, rank markets by lowercase hexadecimal SHA256 of:

`<v0.3-selection-seed>|<event-id>|<market-id>`

The first **two** markets in that deterministic order are the only event candidates eligible to reach CLOB acquisition. If an event contains only one structurally eligible market, that single market is the event's only candidate.

No third market from an event may substitute if either of its first two deterministic candidates later fails CLOB validation.

This differs intentionally from v0.1/v0.2, which allowed one deterministic market per parent event. The within-event cap is fixed before the fresh v0.3 query.

## CLOB snapshot

For the Yes token of every deterministic event candidate, freeze raw responses and timestamps from:

- best bid: `GET https://clob.polymarket.com/price?token_id=<YES>&side=BUY`;
- best ask: `GET https://clob.polymarket.com/price?token_id=<YES>&side=SELL`;
- midpoint: `GET https://clob.polymarket.com/midpoint?token_id=<YES>`.

The bid and ask response must contain numeric `price` values.

Use the v0.2 frozen midpoint alias rule:

1. if exactly one of `mid` or `mid_price` is present, parse that field;
2. if both are present, both must be numeric and exactly equal as decimal values, otherwise reject with `conflicting_midpoint_aliases`;
3. if neither is present, reject with `missing_midpoint_field`;
4. nonnumeric accepted fields are `invalid_clob_price`.

Bid, ask, and midpoint must each be strictly between 0 and 1. A candidate is CLOB-valid only if:

- `bid <= midpoint <= ask`;
- `ask - bid <= 0.10`;
- all three responses were acquired successfully in the same collector run.

The canonical baseline probability is the accepted CLOB midpoint. Gamma probability-like fields are not canonical baselines.

CLOB failure does not authorize within-event replacement.

## Final clustered cohort selection

Each CLOB-valid candidate receives an event-balanced deterministic cohort rank using lowercase SHA256 of:

`<v0.3-selection-seed>|<event-id>|<within-event-rank>|<market-id>`

Final selection uses deterministic round-robin by within-event rank:

1. rank all CLOB-valid first candidates (`within_event_rank = 1`) globally by SHA256 of `<seed>|1|<event-id>|<market-id>` and include them in that order;
2. then rank all CLOB-valid second candidates (`within_event_rank = 2`) globally by SHA256 of `<seed>|2|<event-id>|<market-id>` and append them in that order;
3. stop at 80 selected markets or when no candidates remain.

This rule prioritizes one market per available event before admitting second markets, limiting cluster concentration without semantic selection.

No later replacement occurs.

## Immutable custody payload

The artifact must freeze at least:

- all raw Gamma keyset pages;
- all raw CLOB responses for attempted event candidates;
- normalized universe identity/hash metadata;
- complete eligibility/candidate/CLOB/selection ledger and reason codes;
- selected cohort JSONL;
- acquisition receipts and hashes;
- source URLs, request parameters, request timestamps, and code commit;
- this protocol commit;
- selected contract question, rules/description, source locators, IDs/slugs, outcomes/token IDs, scheduled end time, category, volume/liquidity, and canonical CLOB snapshot inside the artifact;
- `within_event_rank` and parent event ID for cluster-aware downstream analysis;
- SHA256 of each selected canonical contract object.

Workflow logs may print only aggregate counts, cluster-size counts, reason-code counts, hashes, and acquisition status. They must not print question text, description, category, slugs, probability values, outcome information, or other semantic market content before the evidence/forecaster protocol is frozen.

## No model inference in custody

Custody v0.3 must not invoke an LLM or forecast model, calculate model-versus-market scores, inspect later outcomes, or access the reserved 73-case holdout.

If both development-forecaster authorization floors are met, a separate evidence/forecaster preregistration must be committed before selected semantic content is manually inspected or any model forecast is produced.

## Required clustered analysis for the later forecaster protocol

Because v0.3 intentionally contains correlated markets from some parent events, later analysis must not treat all selected rows as independent.

Before any forecast is produced, the forecaster/analysis protocol must freeze at least:

- exact model identity/version and inference settings;
- timestamp-safe evidence acquisition and freeze procedure with evidence cutoff at or before each row's `source_cutoff_at`;
- exact prompt and machine-readable output schema;
- deterministic no-evidence / model-failure behavior;
- probability clipping/transformation rules fixed before outcomes;
- paired Brier-score difference versus the frozen market midpoint;
- paired log-loss difference versus the frozen market midpoint;
- **primary event-balanced estimand**: compute each row's paired score difference, average those differences within parent event, then average equally across parent events;
- uncertainty by resampling **parent events as clusters**, carrying all selected markets from a resampled event together;
- leave-one-event-out sensitivity;
- concentration diagnostics reporting the contribution of the largest positive and negative event clusters;
- secondary row-level metrics labeled descriptive and not treated as independent-observation inference;
- explicit model/evidence failure denominator;
- label balance and calibration reporting after outcomes exist;
- no post-hoc category filtering, threshold tuning, market exclusion, or prompt selection based on v0.3 outcomes.

No confirmatory edge claim may be made from v0.3 itself. v0.3 may inform model/prompt/system selection for a later independent evaluation, but that selection consumes v0.3 for development.

## Later resolution stopping rule

Cohort membership never changes after custody.

Resolution review occurs only under a separately frozen resolution policy. Development analysis is authorized after either every selected case reaches a terminal adjudication state or 90 days elapse after the latest selected scheduled end time, whichever protocol-defined stopping condition is later frozen before outcomes are inspected.

Cancelled, ambiguous, unresolved, or unverifiable cases remain in accounting and are never replaced.

## Holdout boundary

The existing reserved 73-case holdout remains inaccessible during v0.3 custody, evidence collection, prompt/model development, and exploratory scoring. Any later use of that holdout requires a separately frozen final evaluation protocol after v0.3 development decisions are complete.
