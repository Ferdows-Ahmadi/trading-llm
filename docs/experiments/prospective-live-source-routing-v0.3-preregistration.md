# Prospective Live Source Routing v0.3 — Preregistration

Status: **frozen before first v0.3 market-universe query**.

Experiment ID: `prospective-live-source-routing-v0.3`

The Git commit that first contains this preregistration is the protocol identity. All executable v0.3 selection/acquisition/forecast code must bind that exact commit before any live market selection occurs.

## Purpose

Evaluate whether resolution-aware evidence acquisition changes model forecasts in a more decision-relevant way than an exact-question Google News RSS baseline while holding the Polymarket prior, model identities, prompt family, residual mapping, inference settings, and selected markets fixed.

This is a development experiment only. It is not a confirmatory trading-edge test, does not authorize a profitability claim, and does not authorize live-money trading.

The frozen v0.1 and v0.2 cohorts remain closed to rerun, repair, evidence refresh, forecast modification, or early outcome use.

## Preselection model freeze

A fresh local model identity freeze was completed before any v0.3 market selection.

Frozen at: `2026-09-18T16:54:13.068215Z`

Frozen model-manifest SHA256:

`440d3623c08082b724e5685975fdb1062a68e9796d9fbe1e20fabf5422667310`

Frozen models:

- `llama3.1:8b` — `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`
- `qwen3.5:9b` — `sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`
- `deepseek-r1:8b` — `sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763`

The selector must verify the exact frozen model-manifest bytes by SHA256 before the first market-universe request. The manifest itself records that market selection, evidence access, model inference, outcome lookup, and reserved-holdout access were all false at freeze time.

At forecasting time, the local Ollama registry must again match all three frozen tag/digest pairs exactly.

## Cohort

Target cohort: 12 markets from 12 distinct parent events.

Selection horizon: scheduled end between 7 and 30 days after the frozen selection snapshot.

Reuse the v0.2 structural market eligibility rules, including the existing minimum volume, minimum liquidity, valid Yes token, active/unresolved market state, and contract metadata requirements.

No topic/category filter is permitted.

Presence of a usable HTTP(S) resolution-source URL is **not** an eligibility filter. Markets without a usable direct locator remain in the experiment and naturally produce Condition B equal to Condition A when no direct source can be admitted.

Selection seed:

`prospective-live-source-routing-v0.3-selection-seed-2026-09-18`

Within each parent event, select one deterministic representative. Rank those representatives using the frozen seed and select the first 12.

No replacement is permitted after selection for evidence failure, source-routing failure, CLOB failure, model failure, topic, or apparent evidence quality.

## Timing and execution order

For each selected market:

1. begin acquisition no later than 120 minutes after the selection snapshot;
2. capture Condition A RSS evidence;
3. attempt Condition B resolution-source retrieval using the same acquisition session;
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

A successful acquisition may therefore produce different availability states per condition. Each condition receives its own frozen `verified_complete` or `verified_empty` state. Only an overall RSS/capture contract failure is `retrieval_failure`.

## CLOB comparator

After both evidence conditions are frozen, acquire the selected market's Yes-token:

- best bid;
- best ask;
- midpoint.

The existing prospective CLOB validation contract applies: all values must lie strictly inside (0,1), midpoint must lie within bid/ask, spread must be non-negative and within the existing maximum-spread rule.

The identical frozen midpoint is the market prior for Condition A and Condition B.

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

Freeze execution order as model order above, then Condition A followed by Condition B for each market.

Use the same residual-v2 prompt family and output schema already used by v0.2, with:

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

Forecast operational success requires every frozen model-condition cell on every forecast-ready row to end in one of:

- `model_evaluated`
- `model_failure_noop`
- `verified_empty_noop`

Rows that failed acquisition remain explicit `acquisition_failure_no_forecast` records for every model-condition pair.

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

No v0.3 outcome lookup is permitted before every forecast is frozen.

After market resolution under a separately documented adjudication/scoring stage, compute paired Brier and log-loss comparisons using the same frozen market prior.

Primary development comparison: within each model, Condition B versus Condition A.

Secondary diagnostics may compare models, but the 12-market development cohort does not authorize a confirmatory edge, profitability, or statistical-significance claim.

Markets unresolved 30 days after scheduled end are marked unresolved for primary accounting and are not replaced. Later resolution may be reported descriptively.

## Leakage and holdout boundaries

- Reserved 73-case historical holdout remains untouched.
- No v0.1 or v0.2 eventual outcomes may be used to tune v0.3 before all v0.3 forecasts freeze.
- No post-selection market replacement.
- No post-selection prompt/model/mapping/source-rule tuning.
- No manual evidence editing or source substitution.
- No evidence refresh after a row's acquisition is frozen.
- No post-forecast price refresh or forecast modification.
- No outcome lookup before the authorized scoring stage.

## Authorization gate

The first v0.3 market-universe query is authorized only after:

1. this preregistration is committed and its commit SHA is bound into the selector/session implementation;
2. paired Condition A/B custody and forecasting code exists;
3. tests cover direct-source success, direct-source failure fallback, malformed locators, separate A/B empty states, no-overwrite/no-replacement behavior, exact model identities, and paired forecast accounting;
4. Prediction Lab CI passes tests and Ruff on the final implementation commit;
5. local repository is fast-forwarded to that green implementation commit.

Until those conditions are met, no v0.3 selection command should be run.
