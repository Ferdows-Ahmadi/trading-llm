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
   the forecast timestamp.
3. **Unknown stays unknown.** Missing data must never be converted to a favorable or
   neutral signal merely to keep a pipeline running.
4. **Forecasting skill and trading profitability are separate claims.** Better Brier
   score does not imply a tradable edge after spread, fees, slippage, and liquidity.
5. **No silent failures.** Do not use broad exception handlers that continue an
   experiment without surfacing the affected observations.
6. **Raw historical inputs are immutable.** Transform into derived datasets rather
   than rewriting source data.
7. **Do not optimize on the holdout set.** Model/prompt/feature selection must be made
   before the final temporal holdout is evaluated.
8. **Report inconvenient results.** An experiment that loses to the market is useful
   evidence. Do not change evaluation rules to improve a headline metric.
9. **Keep execution deterministic.** When execution work eventually begins, LLMs may
   propose actions but hard-coded risk and validation gates retain final authority.
10. **Never commit secrets or wallet material.** No private keys, seed phrases,
    exchange credentials, API tokens, or funded-wallet identifiers belong in source.

## Required experiment metadata

Every serious experiment should record at least:

- hypothesis and experiment ID
- code/strategy/model version
- data source and data window
- forecast timestamp policy and research cutoff policy
- sample size and category/horizon coverage
- model Brier score and market Brier score
- Brier delta (`model - market`; negative is better)
- model and market log loss
- calibration diagnostics
- known exclusions, failures, and contamination risks

## Current v0.1 scope

Build the truth machine first:

1. normalize resolved prediction-market observations;
2. reject temporally contaminated observations;
3. evaluate model probabilities against the market baseline;
4. slice results by category, market-probability bucket, and forecast horizon;
5. import a real historical dataset;
6. run a genuinely out-of-sample benchmark before adding execution.

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
file and `docs/prediction-market-lab.md`. The correct next task is the earliest
unfinished milestone in that document, not whichever feature sounds most impressive.
