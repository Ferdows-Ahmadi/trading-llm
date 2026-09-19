# Prospective Live Source Routing v0.4 — Preregistration

Status: **frozen before first v0.4 market-universe query**.

Experiment ID: `prospective-live-source-routing-v0.4`

The Git commit that first contains this preregistration is the protocol identity. All executable v0.4 selection/acquisition/forecast code must bind that exact commit before any live market selection occurs.

## Purpose

Repeat the v0.3 paired evidence experiment on a fresh prospective cohort after correcting the adapter-state collision discovered in v0.3.

The scientific comparison remains:

- Condition A: exact-question Google News RSS baseline.
- Condition B: the exact same frozen RSS evidence plus successfully retrieved contract resolution-source material.

The Polymarket prior, frozen local models, prompt family, residual mapping, inference settings, and acquisition ordering remain fixed so the primary development question is whether resolution-aware evidence changes forecast quality.

This is a development experiment only. It is not a confirmatory trading-edge test, does not authorize a profitability claim, and does not authorize live-money trading.

## Preselection model freeze

A fresh local model identity freeze was completed before any v0.4 market selection.

Frozen at: `2026-09-19T08:05:02.411677Z`

Frozen model-manifest SHA256:

`3cac3f0949f844e39fb052d104d2a284f4eeef2ba3c1674263c2ba99c4bfa514`

Frozen models:

- `llama3.1:8b` — `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`
- `qwen3.5:9b` — `sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`
- `deepseek-r1:8b` — `sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763`

The selector must verify the exact frozen model-manifest bytes by SHA256 before the first market-universe request.

At forecasting time, the local Ollama registry must again match all three frozen tag/digest pairs exactly.

## v0.3 failure correction

v0.3 reused one residual adapter instance for both Condition A and Condition B within each model. The adapter correctly rejects a second decision for the same `question_id`, so Condition B failed after Condition A had already occupied the decision namespace.

v0.4 freezes the correction:

- each model-condition pair owns an independent adapter instance and independent decision-record namespace;
- Llama A and Llama B are separate adapters;
- Qwen A and Qwen B are separate adapters;
- DeepSeek A and DeepSeek B are separate adapters;
- the original market `question_id` is preserved in both conditions;
- no synthetic question IDs are permitted merely to bypass duplicate detection.

## Cohort

Target cohort: 12 markets from 12 distinct parent events.

Selection horizon: scheduled end between 7 and 30 days after the frozen selection snapshot.

Reuse the v0.3 structural market eligibility rules, including existing minimum volume, minimum liquidity, valid Yes token, active/unresolved market state, and contract metadata requirements.

No topic/category filter is permitted.

Presence of a usable HTTP(S) resolution-source URL is not an eligibility filter.

Selection seed:

`prospective-live-source-routing-v0.4-selection-seed-2026-09-19`

Within each parent event, select one deterministic representative. Rank those representatives using the frozen seed and select the first 12.

No replacement is permitted after selection for evidence failure, source-routing failure, CLOB failure, model failure, topic, or apparent evidence quality.

## Timing and execution order

For each selected market:

1. begin acquisition no later than 120 minutes after the selection snapshot;
2. capture Condition A RSS evidence;
3. attempt Condition B resolution-source retrieval in the same acquisition session;
4. freeze both evidence conditions and all source receipts;
5. only then acquire Yes-token bid, ask, and midpoint;
6. freeze raw CLOB responses;
7. require the market snapshot timestamp to be no earlier than evidence completion;
8. require the market snapshot to fall within 15 minutes of that market's evidence-capture start.

All 12 acquisition attempts must complete before any model inference begins.

Acquisition operational-success floor: at least 10 of 12 markets must be forecast-ready. Failure to reach 10 forecast-ready rows blocks forecasting. Failed rows are not replaced.

## Condition A — exact-question Google News RSS

For each selected market:

- provider: Google News RSS;
- query: exact Polymarket question text, stripped only of surrounding whitespace;
- locale: `hl=en-US`, `gl=US`, `ceid=US:en`;
- retain up to the first 5 unique valid RSS items in provider order;
- freeze raw RSS bytes before parsing;
- no manual filtering, rewriting, source substitution, article browsing, or downstream retrieval.

A successful zero-item RSS response is `verified_empty`.

## Condition B — resolution-aware routed evidence

Condition B always begins with the exact frozen Condition A items.

Use the contract's frozen `resolution_sources` locators in original order. Consider at most the first 2 unique locators that are syntactically valid public HTTP(S) URLs on ports 80/443/default.

For each admitted URL:

- direct GET only;
- at most 3 redirects;
- 20-second request timeout;
- 2 total attempts for transient failure;
- maximum response body 2 MiB;
- accept only textual HTML/plain text/JSON/XML-like content;
- freeze successful raw bytes and SHA256 before text extraction;
- deterministically extract at most 12,000 normalized visible characters;
- require at least 100 extracted characters for admission.

Malformed, non-HTTP(S), unsafe, non-text, oversized, too-short, blocked, or failed locators are recorded but never manually replaced.

If no direct resolution source is admitted, Condition B is exactly the Condition A evidence item sequence.

Each condition receives its own frozen `verified_complete` or `verified_empty` state. Only an overall RSS/capture contract failure is `retrieval_failure`.

## CLOB comparator

After both evidence conditions are frozen, acquire the selected market's Yes-token best bid, best ask, and midpoint.

The existing prospective CLOB validation contract applies. The identical frozen midpoint is the market prior for Condition A and Condition B.

CLOB transport/validation/binding failure makes that selected row non-forecast-ready. The row is not replaced.

## Forecasting

For each forecast-ready market, run all three frozen local models under both evidence conditions.

Paired cells per forecast-ready market:

- Llama 3.1 8B × Condition A
- Llama 3.1 8B × Condition B
- Qwen 3.5 9B × Condition A
- Qwen 3.5 9B × Condition B
- DeepSeek-R1 8B × Condition A
- DeepSeek-R1 8B × Condition B

Freeze execution order as model order above, with separate A and B adapter instances per model.

Use the same residual-v2 prompt family and output schema already used by v0.3, with:

- identical market prior across A/B;
- temperature 0;
- seed 0;
- local Ollama inference;
- 1,200-second request timeout;
- no browsing, tools, retrieval, memory injection, or cross-condition communication;
- exactly one model request for each evidence-bearing model-condition cell.

Residual logit mapping remains frozen:

- no-op: 0
- weak: ±0.25
- moderate: ±0.50
- strong: ±0.75

For a condition with `verified_empty` evidence, preserve the exact market prior and do not call the model.

For a model request failure, preserve the exact market prior using the existing deterministic model-failure no-op record. No retry is permitted after the single model request.

## Success accounting

v0.4 reports two separate success concepts.

### Terminal safety success

Every forecast-ready model-condition cell must end in one of:

- `model_evaluated`
- `model_failure_noop`
- `verified_empty_noop`

Rows that failed acquisition remain explicit `acquisition_failure_no_forecast` records for every model-condition pair.

### Paired inference success

For every evidence-bearing model-condition cell, the intended single model request must finish as `model_evaluated`.

Verified-empty cells are exempt because the frozen protocol intentionally performs no model call.

If any evidence-bearing cell ends in `model_failure_noop`, paired inference success is false even if terminal safety success remains true.

This stricter metric prevents a run like v0.3 from being summarized as a successful paired inference experiment merely because failures were safely converted to no-ops.

## Pre-resolution diagnostics

After all forecasts are frozen, outcome-blind diagnostics may report:

- Condition A/B evidence-item counts and character volume;
- direct-source attempts and admissions;
- identical-A/B evidence frequency;
- verified-empty frequency by condition;
- action counts;
- abstain/non-abstain counts;
- evidence-strength distributions;
- citation counts;
- within-model A/B action agreement;
- within-model change in logit delta and final probability;
- schema/runtime/model-failure counts.

Manual qualitative inspection of frozen reasoning is allowed only after all forecasts are complete.

These diagnostics do not establish predictive superiority or profitability.

## Outcome boundary and later scoring

No v0.4 outcome lookup is permitted before every forecast is frozen.

After market resolution under a separately documented adjudication/scoring stage, compute paired Brier and log-loss comparisons using the same frozen market prior.

Primary development comparison: within each model, Condition B versus Condition A.

Secondary diagnostics may compare models, but the 12-market development cohort does not authorize a confirmatory edge, profitability, or statistical-significance claim.

Markets unresolved 30 days after scheduled end are marked unresolved for primary accounting and are not replaced. Later resolution may be reported descriptively.

## Leakage and holdout boundaries

- Reserved 73-case historical holdout remains untouched.
- No v0.1, v0.2, or v0.3 outcomes may be used to tune v0.4 before all v0.4 forecasts freeze.
- No post-selection market replacement.
- No post-selection prompt/model/mapping/source-rule tuning.
- No manual evidence editing or source substitution.
- No evidence refresh after a row's acquisition is frozen.
- No post-forecast price refresh or forecast modification.
- No outcome lookup before the authorized scoring stage.

## Authorization gate

The first v0.4 market-universe query is authorized only after:

1. this preregistration is committed and its commit SHA is bound into the selector/session implementation;
2. paired Condition A/B custody and forecasting code exists with isolated adapter state;
3. tests cover same-question A/B independence, empty/non-empty combinations, no-retry/no-overwrite behavior, exact model identities, and paired-success accounting;
4. Prediction Lab CI passes tests and Ruff on the final implementation commit;
5. local repository is fast-forwarded to that green implementation commit.

Until those conditions are met, no v0.4 selection command should be run.
