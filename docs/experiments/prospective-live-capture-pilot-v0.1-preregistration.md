# Prospective live-capture pilot v0.1 preregistration

Status: frozen before the first market-universe query for this pilot.

Experiment ID: `prospective-live-capture-pilot-v0.1`

Purpose: **operational end-to-end pilot only.** This pilot tests whether live evidence capture, market snapshot binding, local model inference, immutable custody, and later adjudication can run reliably. It is not a confirmatory model-versus-market edge test, regardless of eventual scores.

The retired GDELT/Common Crawl historical-reconstruction lane is not reused.

## Pilot cohort

Selection seed:

`prospective-live-capture-pilot-v0.1-selection-seed-2026-09-15`

Target: **8 markets from 8 distinct parent events**.

No second market from the same parent event is permitted in this pilot.

The pilot uses a fresh live Polymarket universe. It does not reuse or reselect any row from the retired 77-market cohort.

Scheduled-end window:

- minimum: selection snapshot + 7 days;
- maximum: selection snapshot + 30 days.

The shorter horizon is chosen only to make an operational pilot resolve in a practical period. It is frozen before acquisition.

## Structural market eligibility

Reuse the frozen v0.3 structural criteria:

1. non-empty market ID, condition ID, question, and end date;
2. market not closed;
3. market active unless explicitly false;
4. order book enabled;
5. accepting orders;
6. exactly two outcomes normalized to Yes/No;
7. exactly two CLOB token IDs mapped one-to-one to outcomes;
8. exact parent event ID available;
9. scheduled end inside the frozen 7-to-30-day window;
10. volume >= 5,000;
11. liquidity >= 1,000;
12. non-empty description and at least one non-empty resolution-source locator.

Unknown/malformed fields fail eligibility. No semantic topic/category filter is permitted.

## Deterministic market selection

Group structurally eligible markets by exact parent event ID.

Within each event, rank markets by lowercase SHA256 of:

`<selection-seed>|<event-id>|<market-id>`

Only the first ranked structurally eligible market from each event is an event candidate.

Rank event candidates globally by lowercase SHA256 of:

`<selection-seed>|pilot|<event-id>|<market-id>`

Select the first 8 event candidates. No later replacement is permitted if evidence capture, CLOB validation, model inference, or eventual adjudication fails.

This selection is blind to evidence availability, category, topic, model opinion, later price movement, and outcome.

## Live evidence source

Pilot discovery provider: **Google News RSS search**.

Frozen endpoint:

`https://news.google.com/rss/search`

Frozen locale parameters:

- `hl=en-US`
- `gl=US`
- `ceid=US:en`

Query: the exact Polymarket question text, unchanged.

For each selected row:

- one live RSS search is initiated;
- transport may retry at most 3 attempts with exponential backoff starting at 2 seconds;
- freeze the successful raw RSS response bytes before parsing;
- retain the first 5 unique valid RSS items in provider order;
- each retained item may use only fields present in the frozen RSS payload: title, link, source, publication metadata, and description/snippet;
- no manual editing, substitution, relevance filtering, article replacement, or post-capture web browsing is permitted in the pilot;
- no Common Crawl, GDELT, Wayback, or historical archive lookup is permitted.

This pilot deliberately uses RSS payload content rather than downstream article-page scraping to minimize operational failure modes. Full-article retrieval may be evaluated only in a later separately frozen protocol.

## Evidence status semantics

For each selected row:

- `verified_complete`: successful provider response and at least one retained evidence item;
- `verified_empty`: successful provider response and zero valid retained evidence items;
- `retrieval_failure`: provider/transport/XML-parse failure after the frozen retry policy or capture-window violation.

`verified_empty` and `retrieval_failure` are never interchangeable.

No failed row is replaced.

## Timing and comparator fairness

The model must never receive evidence newer than the frozen market comparator.

For each selected market, the sequence is:

1. begin live evidence capture;
2. freeze the raw RSS payload and parsed evidence packet;
3. complete evidence capture;
4. acquire the Yes-token CLOB best bid, best ask, and midpoint;
5. freeze the CLOB responses and `market_price_timestamp`;
6. verify `market_price_timestamp >= evidence_capture_completed_at`;
7. verify the market snapshot occurs no later than 15 minutes after `evidence_capture_started_at`;
8. only then authorize model inference.

Thus the market comparator is timestamped **after** the evidence available to the model, eliminating evidence-gathering latency advantage.

If the market snapshot cannot be validly bound inside the 15-minute window, the row is an operational failure and is not replaced.

## CLOB validity

Reuse the frozen v0.3 CLOB rules:

- numeric bid, ask, and midpoint;
- each strictly between 0 and 1;
- `bid <= midpoint <= ask`;
- spread <= 0.10;
- all three requests acquired in the same local capture session;
- midpoint alias handling remains identical to v0.3.

The accepted midpoint is the canonical market probability comparator.

## Forecaster

Freeze the same forecaster family already developed:

- Meta Llama 3.1 8B Instruct;
- Ollama model `llama3.1:8b`;
- expected digest `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`;
- temperature 0;
- seed 0;
- local inference only;
- no browsing/tools;
- one model request per evidence-bearing row.

Residual action mapping remains fixed:

- no-op: 0.00 logit;
- weak: +/-0.25;
- moderate: +/-0.50;
- strong: +/-0.75.

A `verified_empty` row receives exact market-prior no-op without a model call.

A model/provider/schema failure receives exact market-prior no-op and remains in accounting.

## Runtime boundary

Time-sensitive acquisition and inference run on a persistent local machine for the pilot.

GitHub Actions is not an evidence worker.

GitHub remains responsible for:

- source control;
- CI/tests/lint;
- frozen protocol documentation;
- code review;
- later custody of hashed pilot artifacts.

The pilot worker must write immutable local artifacts immediately. Upload/push to GitHub may occur only after the row/session has already been frozen locally.

## Pilot success criteria

The pilot is operationally successful if at least 7 of the 8 selected rows:

- complete evidence capture as `verified_complete` or `verified_empty`;
- bind a valid CLOB market snapshot inside the 15-minute window;
- produce a terminal forecast record or deterministic no-op;
- preserve raw evidence, raw market responses, timestamps, hashes, and model record without leakage.

This threshold is for infrastructure qualification only. It is not a performance threshold and cannot be used to claim forecasting edge.

If fewer than 7 rows succeed, the pilot is frozen as failed. Any redesign requires a new version before additional live acquisition.

## Later outcomes and scoring

No outcomes are inspected during acquisition or forecasting.

After resolution, pilot scores may be computed for debugging only:

- paired Brier difference: model minus frozen market;
- paired log-loss difference: model minus frozen market.

With only 8 distinct events, no statistical edge claim is authorized.

Markets unresolved 30 days after their scheduled end are marked unresolved for this pilot's primary accounting and are not replaced. Any later resolution can be recorded descriptively.

## Holdout boundary

The reserved 73-case holdout remains untouched.

This pilot cannot be used to inspect, select, filter, tune, or otherwise adapt to the reserved holdout.

## Prohibited actions

Before all pilot forecasts are frozen:

- no outcome lookup;
- no post-forecast market-price lookup for decision-making;
- no manual evidence selection;
- no category/topic filtering based on observed evidence;
- no model swap;
- no prompt tuning based on pilot outcomes;
- no extra market substitution;
- no historical reconstruction source;
- no use of the reserved holdout.

Any violation invalidates the affected pilot row and must be documented.
