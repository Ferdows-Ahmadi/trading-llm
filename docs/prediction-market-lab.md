# Prediction Market Lab v0.1

## Purpose

The prediction-market lane exists to answer one question before live trading work is
allowed to begin:

> Can our forecasting system produce genuinely out-of-sample probabilities that are
> better than the market probabilities available at the same time?

The project deliberately starts with measurement rather than execution. A profitable
looking backtest is not evidence if it uses future information, unrealistic prices,
or a weak baseline.

## v0.1 architecture

```text
historical resolved markets
          |
          v
normalized forecast observations
          |
          v
strict temporal leakage validation
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

Each row represents one forecast made at one historical decision time.

Required columns:

| Column | Meaning |
| --- | --- |
| `question_id` | Stable market/question identifier |
| `question_text` | Human-readable forecasting question |
| `forecasted_at` | Exact timestamp when the model forecast is considered made |
| `resolved_at` | Final resolution timestamp |
| `market_price_timestamp` | Timestamp of the market probability used as the baseline |
| `source_cutoff_at` | Latest timestamp allowed among research evidence supplied to the model |
| `market_probability` | Contemporaneous market probability in `[0, 1]` |
| `model_probability` | Forecast-system probability in `[0, 1]` |
| `outcome` | Final binary outcome, `0` or `1` |

Optional columns currently normalized by the package:

- `category` (default `unknown`)
- `model_name` (default `model`)
- `split` (default `unspecified`)

### Temporal invariants

A row is rejected when any of these are true:

- `market_price_timestamp > forecasted_at`
- `source_cutoff_at > forecasted_at`
- `resolved_at <= forecasted_at`
- the same `question_id`, `forecasted_at`, and `model_name` appears more than once

Train/test temporal validation also requires the test period to begin strictly after
the training period ends.

## Evaluation semantics

The market is not merely another feature. It is the reference forecast we have to beat.

Primary metrics:

- model Brier score
- market Brier score
- Brier delta = `model_brier - market_brier`
- Brier skill score versus the market
- model and market binary log loss
- expected calibration error for both
- fraction of observations where model squared error is lower than market squared error

Interpretation:

- negative Brier delta is good;
- positive Brier skill score is good;
- neither result alone proves profitability.

Reports are also sliced by:

- category
- market-probability bucket
- forecast horizon

The goal is to discover narrow regions where the system has repeatable skill, rather
than forcing a global claim that "AI beats prediction markets."

## Local usage

```bash
cd packages/prediction-lab
python -m venv .venv
# activate the environment for your shell
pip install -e ".[dev]"
pytest
prediction-lab examples/sample_forecasts.csv
```

The CLI prints a JSON evaluation report. It can also write one to disk:

```bash
prediction-lab examples/sample_forecasts.csv --output reports/demo.json
```

## Milestones

### M0 - Evaluation foundation

Status: implemented in the initial v0.1 branch.

- [x] strict forecast-row data contract
- [x] UTC timestamp normalization
- [x] future-price and future-source leakage guards
- [x] temporal holdout overlap guard
- [x] Brier score and Brier skill score
- [x] binary log loss
- [x] calibration table / expected calibration error
- [x] category, probability-bucket, and horizon slices
- [x] CLI and sample dataset
- [x] unit tests

### M1 - Real historical dataset adapter

Next target.

- [ ] choose a reproducible initial slice from `prediction-market-analysis`
- [ ] document exact source version / retrieval instructions
- [ ] map resolved markets and historical probability snapshots into the v0.1 contract
- [ ] add deterministic validation and duplicate handling
- [ ] produce a frozen development dataset and a later temporal holdout
- [ ] add tests against edge cases found in real data

### M2 - First forecasting interface

- [ ] define a minimal forecaster protocol
- [ ] add trivial baselines (market, 50%, category/base-rate where defensible)
- [ ] add a structured research forecast inspired by `forecasting-tools`
- [ ] preserve all evidence timestamps used by a forecast
- [ ] keep model/provider concerns behind an adapter

### M3 - Out-of-sample benchmark

- [ ] freeze forecasting logic before final holdout evaluation
- [ ] evaluate at least 200 resolved holdout observations before strong conclusions
- [ ] compare directly with the same-question market baseline
- [ ] analyze category/horizon/probability slices
- [ ] record contamination risks and failed cases

A model that fails to beat the market is not a project failure. It is an experimental
result that tells us not to spend money automating a nonexistent edge.

### M4 - Tradability gate

Only starts if M3 produces a repeatable forecasting edge.

- [ ] use executable prices rather than idealized midpoint probabilities
- [ ] include spread, fees, slippage, and liquidity
- [ ] define uncertainty and minimum-edge margins
- [ ] evaluate whether forecasting skill survives trading costs

### M5 - Shadow / paper execution

Only after M4.

- [ ] evaluate NautilusTrader integration
- [ ] deterministic risk limits
- [ ] shadow mode before funded accounts
- [ ] reconcile forecasts, proposed trades, fills, and outcomes

## Explicitly deferred

Until the evidence justifies them, do not spend engineering time on:

- TradingAgents orchestration
- cross-venue arbitrage / Pytheum integration
- market-making / `hftbacktest`
- autonomous long-term memory
- LLM routing infrastructure
- funded Polymarket or Kalshi accounts
- VPS deployment

Those are possible later components, not prerequisites for discovering whether an edge
exists.
