# Prediction Market Lab Research State

This file is the durable handoff for the research lane. Treat Git history, frozen artifacts,
and this document as the canonical project state when a chat transcript is incomplete.

## Canonical repository state

- Repository: `Ferdows-Ahmadi/trading-llm`
- Active branch: `research/prediction-market-lab-v0.1`
- `main` remains untouched by this research lane.
- Pull request: #1 remains unmerged.
- Pre-Stage-B-hardening reference commit:
  `d2bf52888f19968a5c0e58dec372549196ff3f21`
- The frozen development benchmark SHA-256 is
  `c05cbfa404804789faec779877c839b6655abc317217f182a673b2e91bd9f9a7`.
- Holdout data must be deleted from historical-evidence jobs before discovery or archive
  lookup and must not be used for tuning.

## What has been established

1. The benchmark/evaluation harness is leakage-safe by construction and compares every
   serious forecast against the contemporaneous prediction-market probability.
2. M4 forecasting machinery has been implemented and reviewed. The model-facing evidence
   projection excludes later operational provenance, experiment identities include model
   and evidence identities, and historically unsafe models fail preflight.
3. Stage A historical-news discovery is viable enough for the pilot. GDELT discovery v0.4
   covered 12 of 20 frozen development questions and preserved 111 article URLs.
4. Stage B architecture is viable but its first transport configuration was not. Common
   Crawl capture-index pilot v0.1 completed successfully as a workflow, but among 30
   attempted URLs it found 0 captures, recorded 29 transport failures, and only 1 clean
   no-capture result. The failures were dominated by timeouts and HTTP 503 responses.
   Therefore v0.1 is a transport/reliability result, not evidence that archive coverage is
   zero.

## Current experiment: Stage B v0.2

The immediate task is to measure Common Crawl coverage without confusing provider failure
with absence.

Stage B v0.2 must:

- keep the exact same frozen development benchmark and GDELT v0.4 discovery artifact;
- seed from v0.1 checkpoints;
- reuse successful and definitive no-capture checkpoints;
- retry checkpoints that contain transport failures;
- classify every considered URL as `capture`, `no_capture`, or `transport_failure`;
- use one canonical, scheme-less, exact-page CDX query per crawl collection rather than
  fanning one article out into many scheme/www variants;
- preserve exact path validation and reject homepage or different-page substitutions;
- pace requests and use bounded exponential retry/backoff;
- remain development-only and fetch no WARC article bodies yet.

The first v0.2 recovery run is intentionally bounded to the top discovered URL per question
and two eligible crawl collections. It is a transport-health experiment, not the final
archive-coverage sweep.

## Decision after Stage B v0.2

- If transport failures fall substantially and real captures appear, keep the hardened
  client and resumably expand Stage B across more of the 111 frozen URLs/collections.
- If Common Crawl remains mostly transport-failed despite conservative pacing, stop
  hammering it and evaluate the existing Wayback/CDX fallback as a second archive route.
- Do not infer `no_capture` from a timeout, HTTP 429, HTTP 5xx, or incomplete crawl search.
- Do not proceed to model forecasting merely because the workflow itself exits green.

## Later sequence

Only after Stage B gives defensible capture coverage:

1. Stage C downloads WARC ranges only for verified captures at or before each forecast
   cutoff.
2. Parse article text and freeze a content-addressed historical evidence corpus.
3. Lock one contamination-safe frozen historical model and document its provenance.
4. Run preregistered development-only blind and market-aware forecasts.
5. Compare model Brier/log loss/calibration with the market baseline.
6. Only after the full methodology, evidence, and model are frozen should the untouched
   holdout be evaluated once.
7. Trading profitability, execution costs, venue connectivity, and live/shadow execution
   remain later claims and later milestones.

## Deferred ideas worth revisiting

External review has reinforced several later improvements: larger samples, category and
market-probability-bucket analysis, execution-cost modelling, confidence-decay/retest
tracking, and eventual comparison with external forecasting/execution frameworks. These
are intentionally deferred until M4 has a trustworthy historical evidence path.

## Continuity rule

At the end of every material experiment, update this file with the run ID, commit SHA,
artifact identity, measured result, and next decision. Do not rely on a single chat
conversation as the only project notebook.
