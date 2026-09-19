# Prediction Market Lab Research State

This file is the durable handoff for the research lane. Treat Git history, frozen artifacts,
and this document as the canonical project state when a chat transcript is incomplete.

## Canonical repository state

- Repository: `Ferdows-Ahmadi/trading-llm`
- Active branch: `research/prediction-market-lab-v0.1`
- `main` remains untouched by this research lane.
- Pull request: #1 remains unmerged.
- The frozen development benchmark SHA-256 is
  `c05cbfa404804789faec779877c839b6655abc317217f182a673b2e91bd9f9a7`.
- The final 73-case event-independent holdout remains sealed. No holdout result has been
  consulted for tuning.

## What has been established

1. The benchmark/evaluation harness is leakage-safe by construction and compares every
   serious forecast against the contemporaneous prediction-market probability.
2. M4 forecasting machinery has been implemented and reviewed. Model-facing evidence
   excludes later operational provenance, experiment identities include model/evidence
   identities, and historically unsafe models fail preflight.
3. GDELT historical discovery v0.4 covered 12 of 20 frozen development questions and
   preserved 111 historical article URLs.
4. Common Crawl was tested and rejected for this sample without weakening timestamp or
   exact-page rules. Stage B v0.3, run `34521747701`, produced 12 definitive top-URL
   `no_capture` results, zero transport failures, and zero captures.
5. Wayback/CDX succeeded as fallback archive. Full capture-index v0.3 inspected all 111
   frozen GDELT URLs and recorded 100 verified pre-cutoff exact-page HTML captures, 10
   definitive no-capture results, and 1 lookup failure, while preserving capture coverage
   for all 12 questions that had GDELT discovery.
6. Wayback content freeze v0.2, run `34527997994`, froze 94 historical content items from
   the 100 verified captures, with 6 body failures and coverage on all 12 discoverable
   pilot questions. Artifact digest:
   `sha256:da57d4f914844fd093d899cfb24f346e4577ccaaf880de95d2057f14883713ad`.
7. Deterministic lexical relevance filtering (`lexical-relevance-v1`) inspected all 94
   frozen items, kept 16, dropped 78, retained relevant evidence for 8 of 20 pilot questions,
   and explicitly kept 12 zero-evidence questions. Run `34529685281`; filtered fixture hash:
   `6c5d203feb47b13f15cfe46bbf58d327629544bd9aba61bfed140c30feb92108`.
8. The exact 20-question development pilot was independently frozen in run `34555783305`.
   Artifact digest:
   `sha256:c8b24dd5b92fd36625d756ea4f94d98841ce8303757190d2c6385c27276032c7`.
9. Meta Llama 3.1 8B Instruct provenance is checked in at
   `docs/models/meta-llama-3.1-8b-instruct-provenance.json`, using the conservative normalized
   knowledge cutoff `2023-12-31T23:59:59Z` and release date `2024-07-23T00:00:00Z`.
10. The hosted deterministic smoke experiment completed the full 20-question development
    chain in both blind and market-aware modes with 20/20 forecasts and zero failures. Its
    probability scores are orchestration diagnostics only, not scientific evidence.

## Real Llama 3.1 8B development experiment v0.1

The first real-model development experiment completed successfully as a workflow, using a
fresh GitHub-hosted CPU runner with local Ollama inference and no model tools/web retrieval.
The holdout was not accessed.

- Workflow: `.github/workflows/hosted-llama31-development-v0.1.yml`
- Code commit: `2ea2df58e2ac18dd494df1e932bd4bce0dacb3b2`
- Workflow run: `34559107646`
- Workflow conclusion: success
- Output artifact: `llama31-8b-development-v0.1`
- Artifact ID: `10185059259`
- Artifact digest:
  `sha256:52ffad8dfd4a6ad4d1b59ddf9de6b4eb209b6efef94ba67704716ff3db9f99d8`
- Ollama version: `0.34.0`
- Frozen model tag: `llama3.1:8b`
- Frozen model immutable version:
  `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`
- Quantization reported by Ollama: `Q4_K_M`
- Inference host was CPU-only.
- Prompt version: `research-v0`
- Dataset role: `development-only`
- `holdout_accessed=false`

### Blind mode

- Successful forecasts: 14 / 20
- Failed forecasts: 6
- Forecast coverage: 70%
- Model Brier: `0.2742857142857143`
- Market Brier on the same scored subset: `0.0829660677811969`
- Brier delta (model - market): `+0.19131964650451738`
- Model log loss: `0.7325505818661059`
- Market log loss: `0.2647395719788974`
- Per-observation win rate: `0.14285714285714285`
- `model_beats_market=false`
- Immutable report content hash:
  `5e31d162f1206ce34183cd1e42b05ab305ab7345fcbe10bba33b3840ab45328c`

All 6 blind failures were output-contract failures where the model supplied one or more
`cited_source_ids` that were not valid IDs from the supplied evidence payload.

### Market-aware mode

- Successful forecasts: 15 / 20
- Failed forecasts: 5
- Forecast coverage: 75%
- Model Brier: `0.11079374082998988`
- Market Brier on the same scored subset: `0.08810886646245067`
- Brier delta (model - market): `+0.022684874367539215`
- Model log loss: `0.3311987914611635`
- Market log loss: `0.2815489493586177`
- Per-observation win rate: `0.3333333333333333`
- `model_beats_market=false`
- Immutable report content hash:
  `a1e57cb3ca3bb2889f0c73a1b6aba5fa62a023889bee8ba30e4dc4a12379f475`

Four market-aware failures were invalid `cited_source_ids`; one was an Ollama request timeout
on question `1058133`. Therefore 10 of the 11 total mode-level failures were citation-schema
contract failures, not missing dataset rows or archive failures.

The blind and market-aware metrics above are computed on different successful subsets because
of their different failure sets. Do not interpret the raw difference between the two modes as
an exact apples-to-apples paired comparison until structural failures are eliminated and both
modes score the full same development set.

## Current decision

The experiment produced a useful negative/diagnostic result, not evidence of forecast edge.
Blind Llama underperformed the market badly. Market-aware Llama came much closer but still did
not beat the contemporaneous market on the successful subset.

However, the first required action is not prompt tuning, evidence cherry-picking, or holdout
scoring. The preregistered structural rule applies because coverage was only 70% / 75%.

Next action:

1. Harden the structured-output interface so `cited_source_ids` is constrained at generation
   time to the exact source IDs supplied for that question. For zero-evidence questions, the
   schema must permit only an empty citation list. This is an interface-validity fix, not an
   outcome-driven forecasting change.
2. Increase the bounded Ollama inference timeout for the hosted CPU path so a single slow
   generation does not create an avoidable missing forecast.
3. Add regression tests for invalid citation attempts and zero-evidence questions.
4. Re-run the exact same frozen 20-question development pilot, evidence fixture, model digest
   lineage, and `research-v0` forecasting methodology in blind and market-aware modes.
5. Require 20/20 structurally valid forecasts in both modes before interpreting skill.
6. After a full-coverage rerun, compare Brier, log loss, calibration, paired per-question
   errors, and probability buckets on the same 20 cases. Only then decide whether development-
   only methodology work is justified.
7. The 73-case holdout remains sealed until a final methodology is preregistered and frozen.

## What not to do yet

- Do not score the holdout.
- Do not merge PR #1 into `main`.
- Do not connect wallets or execute trades.
- Do not tune by deleting zero-evidence cases or selecting only favorable questions.
- Do not call the current result profitable or claim market-beating skill.

## Later milestones

If a full-coverage development methodology becomes promising, preregister the exact final
methodology and freeze data/evidence/model/prompt/config identities before one untouched
holdout evaluation. Trading profitability, execution costs, venue connectivity, paper
trading, and live execution remain later claims after forecast skill is established.

## Continuity rule

At the end of every material experiment, update this file with the run ID, commit SHA,
artifact identity, measured result, and next decision. Do not rely on a single chat
conversation as the only project notebook.
