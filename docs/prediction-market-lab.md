# Prediction Market Lab v0.1

## Purpose

The prediction-market lane exists to answer one question before live trading work is allowed to begin:

> Can our forecasting system produce genuinely out-of-sample probabilities that are better than the market probabilities available at the same time?

The project deliberately starts with measurement rather than execution. A profitable-looking backtest is not evidence if it uses future information, unrealistic prices, or a weak baseline.

## v0.1 architecture

```text
historical resolved markets
          |
          v
fixed-lead benchmark builder
          |
          v
frozen development + temporal holdout
          |
          v
sanitized forecaster input
          |
          v
model probability vs market probability
          |
          v
Brier / log loss / calibration / slices
          |
          v
keep, reject, or refine the forecasting hypothesis
```

No live wallet or order path belongs in this phase.

## Data contract

Each case contains the historical question, a contemporaneous market probability, final binary outcome, and strict temporal cutoffs. Forecasters do not receive the final outcome or observed resolution timestamp. Blind runs can additionally hide the market probability.

A row is rejected when the market price or research cutoff is after the forecast timestamp, when resolution is not later than the forecast, or when duplicate forecast observations are detected. Temporal holdout validation requires the holdout period to begin after development ends.

## Evaluation semantics

The market is the reference forecast we have to beat. Primary metrics are model and market Brier score, Brier delta, Brier skill versus market, binary log loss, expected calibration error, and observation-level win rate. Reports are also sliced by category, market-probability bucket, and forecast horizon.

Negative Brier delta is better. Forecasting skill alone does not prove profitability.

## Historical source

The v0.1 benchmark adapter is pinned to:

- repository: `Jon-Becker/prediction-market-analysis`
- revision: `2276382cb616107db8c8647803bffa4a0d7091f8`

The upstream archive is large and must stay outside Git. The benchmark builder accepts an explicitly extracted local `data/` directory. It does not silently download tens of gigabytes.

## Build the first benchmark

The bulk v0.1 builder currently targets Kalshi because the Becker schema provides direct trade timestamps and finalized outcomes. The existing Polymarket adapter remains available for smaller in-memory slices; a memory-efficient Polymarket bulk builder is deliberately deferred.

For each resolved Kalshi market, the builder selects the latest valid trade no later than the requested lead time before the market close. It keeps one case per question, can deterministically cap the dataset across the time span, then reserves the newest fraction as an untouched holdout.

```bash
cd packages/prediction-lab
python -m pip install -e ".[dev]"

prediction-lab-build /path/to/extracted/data \
  --minimum-lead 7D \
  --min-volume 100 \
  --max-questions 1000 \
  --holdout-fraction 0.25 \
  --output-dir data/prediction-lab/benchmark-v0.1
```

The command writes `development.csv`, `development.manifest.json`, `holdout.csv`, `holdout.manifest.json`, and `benchmark-summary.json`. Frozen datasets are SHA-256 verified before reuse.

## Run deterministic baselines

Before any LLM is introduced, score three controls on the untouched holdout:

- the market itself;
- constant 50%;
- a binned calibration model fitted only on development outcomes.

```bash
prediction-lab-baselines \
  data/prediction-lab/benchmark-v0.1/development.csv \
  data/prediction-lab/benchmark-v0.1/development.manifest.json \
  data/prediction-lab/benchmark-v0.1/holdout.csv \
  data/prediction-lab/benchmark-v0.1/holdout.manifest.json \
  --output data/prediction-lab/benchmark-v0.1/baselines.json
```

The market baseline is a scientific control. Its model Brier must equal market Brier and its Brier delta must be zero. If it ever appears to beat itself, the evaluator is broken.

## Milestones

### M0 - Evaluation foundation

Status: implemented.

- [x] strict forecast-row data contract
- [x] UTC timestamp normalization
- [x] future-price and future-source leakage guards
- [x] temporal holdout overlap guard
- [x] Brier score and Brier skill score
- [x] binary log loss
- [x] calibration / expected calibration error
- [x] category, probability-bucket, and horizon slices
- [x] CLI, sample dataset, tests, and CI

### M1 - Real historical benchmark machinery

Status: implemented; real data still needs to be run through it.

- [x] Becker Kalshi Parquet bulk builder using DuckDB
- [x] Becker Polymarket/Kalshi schema adapters
- [x] one observation per resolved question
- [x] fixed lead-time selection
- [x] conservative close/end-time resolution boundary
- [x] deterministic temporal cap and holdout cutoff
- [x] SHA-256 frozen development/holdout manifests
- [x] source revision and selection-policy provenance

### M2 - Deterministic baselines

Status: implemented.

- [x] market control
- [x] constant 50% control
- [x] development-only binned calibration model
- [x] baseline holdout report CLI

### M3 - First real benchmark run

Next target.

- [ ] run 300-1000 resolved markets through the builder
- [ ] freeze the holdout before model development
- [ ] record market, 50%, and calibration baseline results
- [ ] inspect benchmark quality and any schema anomalies

### M4 - First research forecaster

Only after M3 is trustworthy.

- [ ] timestamp-bounded source retrieval
- [ ] base-rate research
- [ ] evidence update
- [ ] adversarial critique
- [ ] final probability
- [ ] cache source/model artifacts for reproducibility
- [ ] run blind and market-aware variants

### M5 - Tradability gate

Only if forecasting skill survives out-of-sample testing.

- [ ] executable prices rather than idealized midpoint probabilities
- [ ] spread, fees, slippage, and liquidity
- [ ] uncertainty and minimum-edge margins

### M6 - Shadow / paper execution

Only after M5.

- [ ] evaluate NautilusTrader integration
- [ ] deterministic risk limits
- [ ] shadow mode before funded accounts
- [ ] reconcile forecasts, proposed trades, fills, and outcomes

## Codex handoff rule

Do not spend Codex credits on deterministic benchmark plumbing. Codex becomes useful when the pipeline below is proven on real data:

```text
historical source
  -> frozen development/holdout
  -> deterministic baselines
  -> trusted evaluation report
```

The first genuinely Codex-worthy task is the timestamp-bounded research/LLM forecasting pipeline at scale.
