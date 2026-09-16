# Prospective Live Source Routing v0.3 — Design Draft

Status: **design draft only**. No v0.3 market-universe query, evidence acquisition, model inference, outcome lookup, or reserved-holdout access is authorized by this document.

Experiment ID: `prospective-live-source-routing-v0.3`

## Purpose

Test whether resolution-aware evidence acquisition produces more decision-relevant evidence than the v0.2 exact-question Google News RSS baseline, while holding the market prior and forecasting models fixed.

This is a development experiment, not a confirmatory trading-edge test and not an authorization for live-money trading.

The frozen v0.1 and v0.2 cohorts remain closed to rerun, repair, evidence refresh, forecast modification, or early outcome use.

## Core comparison

For every forecast-ready v0.3 market, create two frozen evidence conditions from the same pre-inference acquisition session:

### Condition A — baseline RSS

Reuse the v0.2 baseline:

- Google News RSS search;
- exact Polymarket question as query;
- frozen US English locale;
- first 5 unique valid items in provider order;
- frozen raw RSS bytes before parsing;
- no manual filtering or substitution.

### Condition B — resolution-aware evidence

Start from the exact `resolution_sources` locators frozen in the selected Polymarket contract metadata.

For each market:

1. retain the same baseline RSS packet from Condition A;
2. inspect the frozen resolution-source locators deterministically in original order;
3. for up to the first 2 locators that are valid HTTP(S) URLs, attempt direct bounded retrieval;
4. freeze successful raw response bytes and SHA256 before extraction;
5. accept only successful text/html, text/plain, application/json, or XML-like textual responses;
6. enforce a bounded response size and timeout;
7. deterministically extract readable text or canonical JSON/XML text locally;
8. append successful resolution-source material to the routed evidence packet without deleting or rewriting the baseline RSS evidence.

If a resolution-source locator is not an HTTP(S) URL, it is recorded but not manually transformed into a different source.

If all direct resolution-source retrieval fails, Condition B remains valid and falls back to the exact Condition A RSS evidence plus the recorded source locators. Retrieval failure does not permit manual replacement.

## Why this design

The v0.2 experiment showed that the multimodel pipeline works but article enrichment produced 0 successes from 27 attempts, while several RSS packets were only loosely related to the exact market resolution criteria.

The Polymarket contract already stores the source or locator intended to resolve the market. Using that metadata as the primary routing clue is more general and auditable than maintaining an expanding hard-coded list such as GitHub Status, AI leaderboards, election sites, finance sites, and sports feeds.

Topic-specific adapters may be added in later experiments only after this generic resolution-source-first approach is evaluated.

## Cohort concept

Planned target: 12 markets from 12 distinct parent events.

Reuse the v0.2 structural criteria and 7-to-30-day scheduled-end horizon unless changed before preregistration freeze.

No topic/category filter should be added merely to obtain easier sources. No market may be replaced after evidence, CLOB, model, or retrieval failure.

Selection must use a new deterministic v0.3 seed and must not run until the final preregistration is frozen.

## Market comparator and timing

For each selected market, all evidence for both conditions must be frozen before the CLOB comparator is captured.

Planned order:

1. baseline RSS capture;
2. direct resolution-source retrieval attempts;
3. freeze Condition A and Condition B evidence packets;
4. acquire Yes-token bid, ask, and midpoint;
5. freeze raw CLOB responses;
6. require comparator timestamp no earlier than evidence completion;
7. require the comparator within the bounded acquisition window.

All selected-market acquisition must finish before any model inference starts.

## Forecast comparison concept

Use the same exact frozen local model identities for both evidence conditions. A fresh preselection model-verification receipt should be created for v0.3 even if the digests remain identical to v0.2.

For each model and each forecast-ready market:

- run once on Condition A baseline evidence;
- run once on Condition B resolution-aware evidence;
- use the identical frozen Polymarket prior;
- use the same prompt family, residual mapping, temperature, seed, and output schema;
- no tools, browsing, retrieval, or cross-condition communication during inference.

This paired design isolates the effect of evidence condition within each model.

## Pre-resolution diagnostics

Outcome-blind diagnostics may include:

- direct resolution-source retrieval success/failure counts;
- evidence item counts and text volume by condition;
- model abstain/non-abstain rate by condition;
- evidence-strength distribution by condition;
- citation counts by condition;
- within-model action agreement between baseline and routed evidence;
- within-model direction/magnitude changes caused by routed evidence;
- model schema/runtime failures;
- manual qualitative inspection of reasoning consistency only after all forecasts are frozen.

These diagnostics do not establish predictive superiority.

## Later scoring concept

After resolution, score each model-condition pair against the same frozen market prior using paired Brier and log-loss differences.

Primary development comparison should be within-model routed evidence versus baseline evidence. Model-versus-model comparisons remain secondary diagnostics.

With a small development cohort, no confirmatory edge claim is authorized.

## Holdout and leakage boundaries

- Reserved 73-case holdout remains untouched.
- No v0.3 outcome lookup before all forecasts are frozen.
- No use of v0.1 or v0.2 eventual outcomes to tune v0.3 before v0.3 forecasts freeze.
- No post-selection source substitution, manual evidence editing, market replacement, or prompt tuning.

## Work required before preregistration freeze

1. implement deterministic resolution-source parsing and bounded fetch;
2. implement paired Condition A / Condition B evidence custody;
3. implement paired forecasting over identical priors;
4. add tests for direct-source success, direct-source failure fallback, malformed locator handling, and no-replacement semantics;
5. run CI;
6. perform a fresh local model identity freeze;
7. finalize and freeze the v0.3 preregistration;
8. only then run the first v0.3 market-universe query.
