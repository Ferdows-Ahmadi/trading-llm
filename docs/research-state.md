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
4. Stage B v0.1 showed that the original Common Crawl transport strategy was unusable: 0
   captures, 29 transport failures, and 1 clean no-capture result across 30 attempted URLs.
   That was a transport result, not evidence of zero archive coverage.
5. Stage B v0.2 substantially improved transport health but exposed another failure mode.
   Run `34518969301` reused the frozen benchmark and GDELT v0.4 artifact, removed the
   holdout, and wrote 11 new top-URL checkpoint decisions before aborting on an unexpected
   Common Crawl HTTP 400. Among those 11 completed decisions, 8 were definitive
   `no_capture` and 3 were `transport_failure`; no capture was found in that small partial
   sample. The run artifact is `commoncrawl-capture-index-v0.2`, artifact ID
   `10169129484`, digest
   `sha256:3d5e5608d6f7e639a11887ea3c8ab4987bef44683ae12b6896e7443a4f692c6d`.
   Its final summary file is stale from v0.1 because v0.2 crashed before rewriting it, so
   checkpoint statuses are the authoritative partial result.
6. Two live CDX diagnostics established that the canonical scheme-less exact query shape is
   valid. Run `34521327099` returned HTTP 200 for a known-good Common Crawl control and
   HTTP 404 `No Captures found` for the target Econotimes article under several equivalent
   exact query forms. Run `34521466639` then showed provider instability directly: the same
   2026-12 target returned HTTP 504, the 2026-08 target returned a clean 404, and even the
   2026-08 known-good control returned HTTP 503. Therefore provider/client HTTP failures
   must remain retryable audit outcomes rather than crashing the whole evidence run.

## Current experiment: Stage B v0.3

The immediate task remains measuring archive coverage without confusing provider failure
with absence. Stage B v0.3 is a bounded recovery run, not a full sweep.

Current recovery changes:

- Stage B v0.2 is frozen as a manual-only historical workflow.
- `CaptureIndexCommonCrawlClient` now treats unexpected Common Crawl 4xx responses as
  collection-level incomplete lookups. It records the HTTP status/body excerpt, continues
  to other eligible collections, and returns a retryable `CommonCrawlTransportError` if no
  valid capture can make the lookup conclusive.
- A regression test covers the exact `400 on one collection + 404 on another` case and
  requires it to remain an auditable incomplete lookup rather than a fatal pipeline error.
- Stage B v0.3 seeds from the partial v0.2 artifact, reuses the 8 definitive no-capture
  checkpoints, and retries only the inconclusive top-URL lookups.
- v0.3 uses two eligible collections, 20-second request timeouts, three retries, five-second
  exponential backoff, and an eight-second minimum request interval.
- Stage B v0.3 workflow run: `34521747701`.
- Launch commit: `5b0ba65eaf6e308e5bfe7ea8fc94372b70a800b3`.
- Holdout remains deleted before any archive lookup.

## Decision after Stage B v0.3

- If transport failures become rare and one or more real captures appear, keep the hardened
  Common Crawl path and resumably expand Stage B across more of the 111 frozen URLs and
  additional eligible collections.
- If the bounded top-URL sample completes cleanly but still produces zero captures, treat
  exact-page Common Crawl coverage as weak for this GDELT-derived sample and move to the
  Wayback/CDX fallback rather than spending more requests proving the same point.
- If provider instability still dominates despite conservative pacing, also move to the
  Wayback/CDX fallback. A timeout, HTTP 429, HTTP 4xx provider failure, HTTP 5xx, or
  incomplete collection search is never `no_capture`.
- Do not proceed to model forecasting merely because a workflow exits green.

## Later sequence

Only after Stage B gives defensible capture coverage:

1. Stage C downloads archived page bodies only for verified captures at or before each
   forecast cutoff.
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
