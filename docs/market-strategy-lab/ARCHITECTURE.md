# Market Strategy Lab Architecture

## End-state product

The intended product is an auditable trading platform where strategy intelligence proposes opportunities but deterministic controls decide whether capital may be risked.

```text
Market / news data
        |
Normalization + timestamps
        |
Feature / structure analysis
        |
Strategy engines
        |-- ACD Fast Scalp
        |-- future swing strategies
        |-- future event/news strategies
        |
Optional LLM contextual intelligence
        |
Candidate trade thesis
        |
Deterministic risk engine
        |
Replay / backtest / paper execution
        |
Broker / exchange execution (future, not authorized in v0.1)
        |
Journal + evaluation + versioned improvement
```

## Design principles

### Deterministic where safety matters

LLMs may eventually help with ambiguity, context, critique, or explanation.

They must not own:

- position sizing;
- leverage;
- max-loss limits;
- account exposure caps;
- kill switches;
- unrestricted order placement.

### Strategy modules are versioned experiments

A strategy is not just code. Its rules, data assumptions, thresholds, cost model and evaluation protocol are part of its version.

### Replay before execution

The system should be able to reconstruct a historical decision using only information available at that time.

### Audit everything

For every candidate setup, record:

- data timestamp;
- session state;
- strategy version;
- input labels/features;
- ACD level source;
- previous trend;
- M15/M5/M1 state;
- momentum state;
- confirmation result;
- entry/stop/target;
- R:R;
- accepted/rejected/unresolved;
- reason.

## Package responsibilities

### `packages/strategy-lab`

Owns strategy contracts, state machines, decision logic and strategy-specific research primitives.

### `packages/backtest`

Should own reusable chronological replay, fills, cost models and performance evaluation rather than ACD-specific business rules.

### `packages/data-connectors`

Should own market/provider adapters and normalization boundaries.

### `packages/analytics`

Can host generic indicators, structural/statistical analysis and reusable market features when they are not strategy-specific.

## ACD v0.1 flow

```text
Session definition (home timezone)
        |
Timezone/DST conversion
        |
40-minute Opening Range
        |
OR High / OR Low
        |
External A/C level provider
        |
Previous-trend state
        |
M15 base direction
        |
M5 support/confirmation
        |
Outer-boundary touch
        |
M1 execution context
        |
Momentum classification
        |
1-candle or ~3-candle confirmation
        |
Structural invalidation stop
        |
Meaningful target
        |
R:R >= 1:2 ?
      /   \
    no     yes
     |      |
 REJECT   CANDIDATE
```

## Boundaries with Prediction Market Lab

Prediction Market Lab and Market Strategy Lab may eventually feed the same larger trading platform, but their experimental artifacts and validation rules remain independent.

Do not reuse protected Prediction Market Lab information as strategy-development data.
