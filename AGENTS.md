# Agent Operating Contract

This repository is currently prioritizing a research-first prediction-market track.
The immediate mission is **not** to automate live trading. It is to determine, with
strict out-of-sample evidence, whether a forecasting system can beat contemporaneous
market probabilities.

## Non-negotiable research rules

1. **The market is the baseline.** Every forecast evaluation must compare the model
   with the market probability observed at the same decision timestamp.
2. **No future information.** Research sources, prices, resolutions, labels, cached
   summaries, memories, and derived features must not contain information newer than
   the forecast timestamp. Persisted operational provenance may contain later metadata
   such as `retrieved_at`, current archive URIs, or content hashes, but that metadata
   must not be exposed to a historical forecasting model. Model-facing evidence should
   contain only information that was actually available by the historical cutoff.
3. **Model weights count as information.** A historical scored forecast may not use a
   model whose training/release window can contain the event outcome. For historical
   evaluation, use a frozen model with a defensible pre-forecast knowledge cutoff.
   Current frontier models belong in forward/live shadow evaluation unless their
   historical contamination risk can be ruled out explicitly.
4. **Related events cannot straddle the final split.** Parent-event siblings seen in
   development must be purged from holdout. Question-level uniqueness is not enough.
5. **Historical prices must be fresh enough for the declared horizon.** The current
   Polymarket benchmark targets seven days before actual close and accepts a selected
   trade only when it is no more than 72 hours older than that target.
6. **Unknown stays unknown.** Missing data must never be converted to a favorable or
   neutral signal merely to keep a pipeline running.
7. **Forecasting skill and trading profitability are separate claims.** Better Brier
   score does not imply a tradable edge after spread, fees, slippage, and liquidity.
8. **No silent failures.** Do not use broad exception handlers that continue an
   experiment without surfacing the affected observations.
9. **Raw historical inputs are immutable.** Transform into derived datasets rather
   than rewriting source data.
10. **Do not optimize on the holdout set.** Model/prompt/feature selection must be made
    before the final temporal holdout is evaluated. Development can be subdivided for
    iteration; the frozen holdout is a final exam, not a tuning dashboard.
11. **Report inconvenient results.** An experiment that loses to the market is useful
    evidence. Do not change evaluation rules to improve a headline metric.
12. **Keep execution deterministic.** When execution work eventually begins, LLMs may
    propose actions but hard-coded risk and validation gates retain final authority.
13. **Never commit secrets or wallet material.** No private keys, seed phrases,
    exchange credentials, API tokens, or funded-wallet identifiers belong in source.

## Required experiment metadata

Every serious experiment should record at least:

- hypothesis and experiment ID
- code/strategy/model version
- model release, knowledge-cutoff, and contamination assumptions
- data source and data window
- forecast timestamp policy and research cutoff policy
- sample size, parent-event count, and category/horizon coverage
- model Brier score and market Brier score
- Brier delta (`model - market`; negative is better)
- model and market log loss
- calibration diagnostics
- known exclusions, failures, staleness, and contamination risks

## Current v0.1 scope

Build the truth machine first:

1. normalize resolved prediction-market observations;
2. reject temporally contaminated observations;
3. evaluate model probabilities against the market baseline;
4. slice results by category, market-probability bucket, and forecast horizon;
5. build and freeze a real historical benchmark;
6. run deterministic controls before introducing an intelligent forecaster.

Explicitly out of scope for v0.1:

- live orders or funded wallets
- autonomous portfolio management
- market making / HFT
- cross-venue arbitrage
- TradingAgents-style multi-agent committees
- long-term agent memory
- production UI work for prediction markets

## Engineering rules

- Python 3.12+ for research code.
- Prefer small, typed modules and deterministic functions.
- Add tests for every temporal or financial invariant.
- Prefer pandas/numpy/DuckDB before introducing heavier dependencies.
- Major dependencies require a concrete capability we cannot reasonably implement or
  test ourselves.
- Keep the existing crypto/forex application intact while the prediction-market lane
  proves itself.
- The archived `Polymarket/py-clob-client` must not be introduced. If direct
  Polymarket connectivity is eventually needed, evaluate the maintained SDK or the
  chosen execution engine at that time.

## Handoff rule

Before asking Codex or another coding agent to expand the project, point it to this
file, `docs/prediction-market-lab.md`, and the current benchmark record under
`docs/benchmarks/`. The correct next task is the earliest unfinished milestone in the
lab document, not whichever feature sounds most impressive.
