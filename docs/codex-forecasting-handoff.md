# Codex Handoff: First Research Forecaster

## Read first

Before changing code, read:

1. `AGENTS.md`
2. `docs/prediction-market-lab.md`
3. `docs/benchmarks/polymarket-public-v0.1-clean.json`
4. `packages/prediction-lab/src/prediction_lab/cases.py`
5. `packages/prediction-lab/src/prediction_lab/evaluation.py`
6. `packages/prediction-lab/src/prediction_lab/forecasters.py`

The deterministic benchmark laboratory already works. Do not redesign it merely because another abstraction is fashionable.

## Mission

Implement the smallest reproducible research-forecasting layer that can be evaluated against the existing market baseline without outcome, timestamp, parent-event, or model-training leakage.

The task ends at probability generation and experiment artifacts. Do **not** add execution, wallets, orders, NautilusTrader, CCXT, TradingAgents, market making, or autonomous strategy mutation.

## Scientific constraints

### Historical model contamination

The clean benchmark covers forecasts from October 2025 through May 2026. A model used for scored historical forecasts must have a defensible release/training/knowledge cutoff before the scored period. Current frontier models that may have learned resolved outcomes are invalid for the historical score.

Design the provider interface so model metadata records at least:

- provider/model identifier
- immutable version or quantization where available
- release date
- claimed knowledge/training cutoff
- local/API execution mode
- contamination assessment

A current frontier model can be used for code generation and forward forecasting, but not silently substituted into the historical benchmark.

### Holdout isolation

Development and holdout are not interchangeable inputs.

- All prompt, feature, model, retrieval, and parsing iteration occurs on development data or an inner validation split derived from development.
- Do not inspect holdout outcomes while designing the forecaster.
- Do not select prompts or models based on holdout Brier.
- The final holdout evaluation is a separate explicit command/artifact.

### Source-time isolation

A historical evidence item must carry an `available_at` or defensible publication timestamp and must satisfy:

```text
available_at <= forecasted_at
```

If historical availability cannot be established, the source is excluded from scored historical evaluation.

Current web search results are not automatically historical evidence. A page currently visible on the web can contain edits or outcome information that did not exist at forecast time.

## Required architecture

Keep the implementation small and composable. Suggested concepts, names may vary if tests make the contract clearer:

### `EvidenceItem`

Required fields:

```text
source_id
source_type
uri_or_reference
title
available_at
retrieved_at
content_hash
text
```

### `EvidencePacket`

Required fields:

```text
question_id
forecasted_at
research_cutoff_at
evidence_items[]
packet_hash
```

Construction must fail closed if any evidence item is newer than the research cutoff.

### `ForecastArtifact`

Required fields:

```text
experiment_id
question_id
forecasted_at
model_metadata
blind_or_market_aware
base_rate_probability
updated_probability
final_probability
confidence_or_uncertainty
critique
cited_source_ids[]
prompt_version
artifact_hash
```

All probabilities must be finite and within `[0, 1]`.

### Forecaster stages

Version 0 should be intentionally simple:

```text
question
  -> base-rate estimate
  -> evidence synthesis/update
  -> adversarial critique
  -> final probability
```

Use structured outputs and reject malformed model responses. Do not silently coerce nonsense into 0.5.

## Blind vs market-aware experiments

Support two otherwise identical modes:

### Blind

The model cannot see the market probability.

Purpose: measure independent forecasting ability.

### Market-aware

The model receives the contemporaneous market probability already present in the sanitized case input.

Purpose: measure whether research can improve on the crowd rather than merely reproduce it.

Both modes must emit artifacts with explicit mode metadata.

## Model adapter

Implement an adapter boundary rather than hard-coding one provider. The first scored historical implementation should favor a local/frozen model whose release predates the benchmark period and fits practical consumer hardware when quantized.

Do not add a paid API requirement just to complete the interface.

An offline deterministic fake model is required for unit tests.

## Retrieval boundary

Do not solve all historical web retrieval in the first commit.

Implement a provider protocol plus a fixture/file-backed provider first, so evidence-time validation, hashing, caching, and model orchestration can be tested without network access.

A real historical source provider can be added only when it can establish what content was available at historical time `T`.

Potential future providers may include versioned archives, historical news corpora, or timestamped document snapshots, but none should bypass the source-time rule.

## Reproducibility and caching

For every scored forecast, persist enough metadata to reproduce the run:

```text
benchmark hash
code commit
experiment config hash
question id
forecast timestamp
model metadata
prompt version
evidence packet hash
raw structured model output
parsed final probability
```

Use content-addressed local files or another simple deterministic cache before introducing infrastructure-heavy databases.

A cache hit must be keyed by inputs that affect the result. It must never reuse an artifact created with evidence newer than the current forecast cutoff.

## Experiment runner

Add a development-only command that can:

1. load a verified frozen development dataset;
2. optionally create an inner temporal/group-independent validation split;
3. construct/load evidence packets;
4. run blind or market-aware forecasts;
5. write immutable forecast artifacts;
6. convert results to the existing evaluation schema;
7. run the existing evaluator;
8. produce a JSON summary with failures explicitly counted.

The runner must be resumable. One failed question must be recorded as a failure, not silently omitted from metrics.

A separate final-evaluation command may read the frozen holdout only after the experiment configuration has been locked and hashed.

## Tests required before handoff back

At minimum, cover:

- evidence newer than forecast cutoff is rejected;
- missing/unknown source time is rejected for historical scoring;
- outcome and observed resolution timestamp never reach the model adapter;
- blind mode never receives market probability;
- market-aware mode receives only the contemporaneous market probability;
- malformed structured model output fails loudly;
- cache keys change when evidence, prompt, model, or mode changes;
- parent-event groups do not cross any inner development/validation split;
- failed forecasts are counted and cannot disappear from the denominator silently;
- deterministic fake-model experiment is reproducible byte-for-byte where intended.

Normal CI must remain network-free.

## Definition of done

Return the work when this path works locally and in CI with fixtures:

```text
verified development dataset
  -> time-safe evidence packet
  -> frozen-model adapter boundary
  -> blind / market-aware structured forecast
  -> immutable forecast artifact
  -> existing evaluator
  -> reproducible experiment report
```

Do not claim forecasting edge. The implementation itself is not evidence. Once the machinery is green, the next scientific task is to select a defensible pre-period model and historical evidence source, then run development experiments before touching the frozen holdout.

## Parallel forward track

Design, but do not necessarily deploy, a separate forward/live-shadow ledger for current models. Forward forecasts avoid model-training leakage because predictions are timestamped before resolution. This track will eventually benefit from the available VPS for persistent scheduling, caches, and artifact storage.
