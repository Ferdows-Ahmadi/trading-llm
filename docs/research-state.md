# Prediction Market Lab Research State

This file is the durable handoff for the research lane. Treat Git history, frozen artifacts,
and this document as the canonical project state when a chat transcript is incomplete.

## Canonical repository state

- Repository: `Ferdows-Ahmadi/trading-llm`
- Active branch: `research/prediction-market-lab-v0.1`
- `main` remains untouched by this research lane.
- Pull request: #1 remains unmerged.
- Pre-Stage-B-hardening reference commit:
  `d2bf52888f19968a5c0e58dec372549196ff3f21`.
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
   `no_capture` and 3 were `transport_failure`; no capture was found. The run artifact is
   `commoncrawl-capture-index-v0.2`, artifact ID `10169129484`, digest
   `sha256:3d5e5608d6f7e639a11887ea3c8ab4987bef44683ae12b6896e7443a4f692c6d`.
   Its final summary file is stale from v0.1 because v0.2 crashed before rewriting it, so
   checkpoint statuses are the authoritative partial result.
6. Two live CDX diagnostics established that the canonical scheme-less exact query shape is
   valid. Run `34521327099` returned HTTP 200 for a known-good Common Crawl control and
   HTTP 404 `No Captures found` for the target Econotimes article under several equivalent
   exact query forms. Run `34521466639` then showed provider instability directly: the same
   2026-12 target returned HTTP 504, the 2026-08 target returned a clean 404, and even the
   2026-08 known-good control returned HTTP 503. Provider/client HTTP failures therefore
   remain retryable audit outcomes rather than silently becoming `no_capture`.
7. Stage B v0.3 completed cleanly and resolved the Common Crawl decision. Workflow run
   `34521747701`, launch commit `5b0ba65eaf6e308e5bfe7ea8fc94372b70a800b3`, reused the
   eight definitive v0.2 checkpoints and retried four inconclusive top-URL checkpoints with
   conservative pacing. Final result: 12 URLs considered, 12 definitive `no_capture`, zero
   transport failures, zero captures, across the 12 pilot questions that had GDELT
   discovery. Artifact `commoncrawl-capture-index-v0.3`, artifact ID `10170048460`, digest
   `sha256:22875bee30fc53344cdd2425e0f9960c8244df8de314c78efbf09062782523e8`.
   This is sufficient to stop spending pilot requests on Common Crawl exact-page coverage.

## Current experiment: Wayback/CDX Stage B fallback v0.1

The preregistered v0.3 decision rule now points to the Internet Archive Wayback CDX route.
The first Wayback experiment is deliberately bounded to the same top discovered URL for
all 12 development questions with GDELT evidence. It measures archive coverage and
transport health only; it does not download archived page bodies and does not run a model.

Wayback v0.1 requirements:

- use the identical frozen development benchmark and GDELT v0.4 discovery artifact;
- remove every holdout file before any archive request;
- inspect only the first unique discovered article URL per pilot question;
- query only captures at or before each question's frozen `source_cutoff_at`;
- require HTTP 200 HTML captures and exact normalized host/path matching;
- classify every lookup as `capture`, `no_capture`, or `transport_failure`;
- never translate HTTP 429, unexpected HTTP 4xx, HTTP 5xx, malformed responses, or network
  failures into `no_capture`;
- checkpoint each lookup and emit deterministic JSONL, CSV audit, and summary artifacts;
- fetch no archived article body during this coverage pilot.

Wayback fallback launch:

- Workflow: `.github/workflows/wayback-capture-index-v0.1.yml`
- Launch commit: `c8025ee0b480a7a2eee78e58513aa43d6f49bc13`
- Workflow run: `34525534259`
- Planned artifact: `wayback-capture-index-v0.1`

## Decision after Wayback v0.1

- If Wayback yields real pre-cutoff captures with acceptable transport reliability, promote
  the inline pilot into a tested reusable archive client/stage, then resumably expand across
  more of the 111 frozen GDELT URLs before fetching bodies.
- If Wayback transport is unreliable, harden request pacing/retries once and repeat the same
  frozen top-URL pilot before changing the evidence sample.
- If Wayback is reliable but exact-page capture coverage is also effectively zero, stop
  treating these GDELT article URLs as a viable historical-evidence source and redesign the
  historical source strategy rather than weakening timestamp or page-identity rules.
- Do not run historical model forecasts until a defensible historical evidence corpus exists.

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
