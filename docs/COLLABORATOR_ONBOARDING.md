# Collaborator Onboarding

Welcome to `trading-llm`.

This repository is a research-first attempt to build an increasingly autonomous trading system without skipping the unpleasant but necessary part where ideas have to survive evidence.

## Mission

The long-term goal is an auditable trading machine that can:

1. ingest market data and context;
2. identify and analyze opportunities;
3. run validated strategy engines;
4. use LLM reasoning where ambiguity genuinely benefits from it;
5. enforce deterministic risk controls;
6. backtest and replay decisions;
7. paper trade;
8. eventually execute with tiny live capital if the evidence justifies it;
9. evaluate every strategy/model version and improve through versioned experiments rather than uncontrolled self-modification.

Project principle:

> **Prove information -> prove tradability -> prove execution -> risk tiny money -> scale evidence, not confidence.**

## The two research lanes

### 1. Prediction Market Lab

The Prediction Market Lab asks whether an intelligence/forecasting layer can add information beyond a strong market-probability baseline.

Its active research work lives on its own branch and has frozen experimental boundaries. It is scientifically independent from the strategy work described below.

### 2. Market Strategy Lab

The Market Strategy Lab asks whether concrete financial-market trading strategies can be formalized, tested, executed realistically, and shown to have positive expectancy after costs.

The first strategy is:

**Strategy 001: ACD Fast Scalp v0.1**

The initial goal is not live trading. It is a faithful, deterministic, auditable implementation of the rules we actually know, plus explicit `UNRESOLVED` states for rules we do not know yet.

## Branching model

Do not work directly on `main`.

Current Market Strategy Lab integration branch:

```text
research/market-strategy-lab-v0.1
```

Create focused feature branches from it, for example:

```text
feat/acd-session-engine
feat/acd-opening-range
feat/acd-trend-structure
feat/acd-backtest
fix/timezone-dst
test/acd-validation-cases
```

Open pull requests back into `research/market-strategy-lab-v0.1` for review.

## Hard boundaries

Do not casually:

- merge unfinished research into `main`;
- modify Prediction Market Lab preregistrations or frozen artifacts;
- inspect or use its protected 73-case holdout;
- retrieve prospective Prediction Market Lab outcomes or post-cutoff prices for adaptation;
- invent missing ACD formulas or thresholds;
- tune strategy rules after looking at evaluation results and then report the same sample as evidence;
- weaken a risk or validity gate just to make a backtest look better;
- place live orders from this research branch;
- treat an LLM opinion as a substitute for deterministic risk controls.

## How to contribute

Before coding:

1. Read `docs/market-strategy-lab/README.md`.
2. Read `docs/market-strategy-lab/ACD_FAST_SCALP_V0.1.md`.
3. Read `docs/market-strategy-lab/UNRESOLVED_RULES.md`.
4. Read `docs/market-strategy-lab/EXPERIMENT_PLAN.md`.
5. Pick a narrow task.
6. Make the smallest change that solves it.
7. Add or update tests.
8. Explain assumptions in the pull request.

If a rule is absent from the source material, do not manufacture it. Mark it unresolved and continue building around a clean interface.

## Definition of progress

Progress is not "the chart looked good" or "the bot won a few trades."

Useful progress includes:

- a previously discretionary rule becomes reproducible;
- a data path becomes timezone-safe;
- a backtest becomes more realistic;
- a hidden assumption becomes explicit;
- a strategy survives unseen data;
- a strategy fails cleanly and is rejected;
- paper execution matches simulation closely;
- live-risk exposure remains impossible until explicitly authorized.

The repository should be understandable without private chat history. If a decision matters to the experiment, document it here.