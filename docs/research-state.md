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
- The final holdout remains sealed. Historical-evidence and development-forecast jobs must
  not contain or inspect holdout files, and no holdout result may be used for tuning.

## What has been established

1. The benchmark/evaluation harness is leakage-safe by construction and compares every
   serious forecast against the contemporaneous prediction-market probability.
2. M4 forecasting machinery has been implemented and reviewed. The model-facing evidence
   projection excludes later operational provenance, experiment identities include model
   and evidence identities, and historically unsafe models fail preflight.
3. Stage A historical-news discovery is viable for the pilot. GDELT discovery v0.4 covered
   12 of 20 frozen development questions and preserved 111 article URLs.
4. Common Crawl was tested and rejected for this evidence set without weakening timestamp
   or page-identity rules. Stage B v0.3, workflow run `34521747701`, resolved all 12 top-URL
   pilot lookups as definitive `no_capture`, with zero transport failures and zero captures.
   Artifact `commoncrawl-capture-index-v0.3`, artifact ID `10170048460`, digest
   `sha256:22875bee30fc53344cdd2425e0f9960c8244df8de314c78efbf09062782523e8`.
5. Wayback/CDX succeeded as the fallback archive. Full capture-index v0.3 inspected all 111
   frozen GDELT URLs and recorded 100 verified pre-cutoff exact-page HTML captures, 10
   definitive no-capture results, and 1 lookup failure, while preserving capture coverage
   for all 12 questions that had GDELT discovery. The full content-freeze workflow consumes
   that fixed capture artifact from run `34526489458`.
6. Wayback archived-body freeze v0.2, workflow run `34527997994`, selected all 100 verified
   capture rows and froze 94 historical content items, with 6 content failures and content
   coverage on all 12 discoverable pilot questions. Artifact `wayback-content-freeze-v0.2`,
   artifact ID `10172516974`, digest
   `sha256:da57d4f914844fd093d899cfb24f346e4577ccaaf880de95d2057f14883713ad`.
7. A preregistered deterministic lexical relevance filter was applied without labels or
   outcomes. Evidence Relevance Filter v0.1, workflow run `34529685281`, inspected all 94
   frozen evidence items, kept 16, dropped 78, kept relevant evidence for 8 of 20 pilot
   questions, and explicitly retained 12 zero-evidence questions. Method version is
   `lexical-relevance-v1`; filtered fixture hash is
   `6c5d203feb47b13f15cfe46bbf58d327629544bd9aba61bfed140c30feb92108`.
   Artifact `evidence-relevance-filter-v0.1`, artifact ID `10172982145`, digest
   `sha256:bf76e2545f3cf30b89199b64c51c109ab51cc0c6cd7b5e3c3c9481be5a285aec`.
8. The exact 20-question development pilot was frozen independently from the GDELT question
   IDs. Development Pilot v0.1, workflow run `34555783305`, produced 20 unique rows and only
   the `development` split. Artifact `prediction-lab-development-pilot-v0.1`, artifact ID
   `10182498879`, digest
   `sha256:c8b24dd5b92fd36625d756ea4f94d98841ce8303757190d2c6385c27276032c7`.
9. Meta Llama 3.1 8B Instruct has a repository provenance record at
   `docs/models/meta-llama-3.1-8b-instruct-provenance.json`. The official Meta source states
   a December 2023 knowledge cutoff and July 23, 2024 release. The record conservatively
   normalizes the cutoff to `2023-12-31T23:59:59Z`. The model is eligible for historical
   scoring only after the exact local Ollama artifact digest is frozen and used as
   `immutable_version`.

## Hosted development forecast smoke v0.1

The full development forecasting chain has now been exercised successfully in hosted CI
using the deterministic fake adapter. This experiment validates orchestration and research
contracts only. The fake adapter has no learned forecasting skill, so its probability scores
are explicitly non-scientific and must never be cited as evidence for or against the trading
hypothesis.

- Workflow: `.github/workflows/development-forecast-smoke-v0.1.yml`
- Launch commit: `85970a793852b5550aad05966bd5fee71260f639`
- Workflow run: `34558325536`
- Result: success
- Input development pilot: run `34555783305`, artifact ID `10182498879`, digest
  `sha256:c8b24dd5b92fd36625d756ea4f94d98841ce8303757190d2c6385c27276032c7`
- Input filtered evidence: run `34529685281`, artifact ID `10172982145`, digest
  `sha256:bf76e2545f3cf30b89199b64c51c109ab51cc0c6cd7b5e3c3c9481be5a285aec`
- Smoke output artifact: `development-forecast-smoke-v0.1`, artifact ID `10183396566`,
  digest `sha256:e7b9829f89a005f50e702a265b82258fd8509b795f46646637e74c8cb90c0c1d`
- The workflow explicitly verified that neither downloaded input contained `holdout*` files.
- Both modes used the exact clean code commit above, not a `+dirty` worktree identity.

Blind smoke result:

- 20 / 20 successful forecasts, 0 failures, 100% forecast coverage.
- Immutable report content hash:
  `67f3c2a3e5ffd44b0641bbe32e3ec26f4203af9c37119d12d6201d95525159a3`.
- Run identity hash:
  `6b974042cbfeaf0c5ccb0eafd0b68c588c1a236410f0f2fcff4775fd5cfc99d8`.
- Fake-model Brier: `0.32374698159449994`; market Brier on this 20-question pilot:
  `0.06795494714602901`. These numbers are smoke diagnostics only.

Market-aware smoke result:

- 20 / 20 successful forecasts, 0 failures, 100% forecast coverage.
- Immutable report content hash:
  `5b62042a5e942addbc097732af57a65fdab7d6fe52b86cb6e709392d1608eada`.
- Run identity hash:
  `efaf1af08ca9688221a09a25f4f67965d705f1d571518604b1f5549a2b7b1f78`.
- Fake-model Brier: `0.12422618127955003`; market Brier on this 20-question pilot:
  `0.06795494714602901`. These numbers are smoke diagnostics only.

The important result is not the fake scores. It is that both blind and market-aware modes
completed the sealed 20-question development chain, persisted and re-validated all 40
forecast artifacts, persisted 40 evidence packets, produced immutable reports, ran the
scorer, and produced no failure artifacts.

## Current experiment: local Llama 3.1 8B development forecast

The next scientific experiment is now unblocked. Run the exact same frozen 20-question
pilot and filtered historical evidence through a locally frozen `llama3.1:8b` artifact via
Ollama. No external tools or web access are allowed during inference.

Before scoring:

1. Pull/acquire `llama3.1:8b` locally without modifying its weights.
2. Read the exact local Ollama model digest and record it as
   `immutable_version=sha256:<64 hex digest>`.
3. Create model metadata from the checked-in Meta provenance record with:
   `provider=Meta`, `model_id=Meta-Llama-3.1-8B-Instruct`, the frozen local digest,
   `release_date=2024-07-23T00:00:00Z`,
   `knowledge_cutoff=2023-12-31T23:59:59Z`, `execution_mode=local`, and an explicit
   `historical-safe` contamination assessment tied to the offline/no-tools execution.
4. Run development-only `blind` first, then `market-aware`, using the same frozen pilot,
   evidence fixture, prompt version, and code commit lineage.
5. Preserve every artifact, failure ledger, report hash, model digest, and exact command.

This first real-model run is a development experiment, not the final claim. Compare its
Brier score, log loss, calibration, per-observation win rate, and probability-bucket results
with the market baseline. Treat the zero-evidence questions as part of the experiment, not
as cases to delete after seeing results.

## Decision after the local Llama development run

- If the model fails structurally or produces malformed outputs, fix the model-interface
  failure without consulting holdout outcomes, then repeat on development.
- If the model runs but clearly underperforms the market, diagnose development-only error
  modes before changing the methodology. Do not rescue the result by cherry-picking cases.
- If either blind or market-aware forecasting shows promising development skill, preregister
  the exact final methodology and freeze all data/evidence/model/prompt/config identities.
- Only after that freeze may the untouched 73-case event-independent holdout be evaluated
  once.
- Trading profitability, fees, execution costs, venue connectivity, wallet control, paper
  trading, and live execution remain later claims and later milestones. Forecast skill is
  necessary evidence, not proof of tradable profit.

## Deferred ideas worth revisiting

External review has reinforced several later improvements: larger samples, category and
market-probability-bucket analysis, execution-cost modelling, confidence-decay/retest
tracking, and eventual comparison with external forecasting/execution frameworks. These
remain secondary until the real-model development experiment is measured cleanly.

## Continuity rule

At the end of every material experiment, update this file with the run ID, commit SHA,
artifact identity, measured result, and next decision. Do not rely on a single chat
conversation as the only project notebook.
