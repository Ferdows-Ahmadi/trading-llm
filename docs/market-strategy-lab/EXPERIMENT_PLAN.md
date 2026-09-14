# ACD Fast Scalp v0.1 — Experiment Plan

## Research question

Can the currently known ACD Fast Scalp rules be implemented reproducibly and, once sufficiently formalized, produce positive expectancy after realistic trading costs on unseen data?

The first milestone is **reproducibility**, not profitability.

## Stage 0 — Collaboration and research boundaries

Deliverables:

- collaborator onboarding;
- lab charter;
- source-based strategy specification;
- unresolved-rule register;
- package/test scaffold;
- draft PR for collaborative work.

Exit condition:

A new contributor can understand the project structure and scientific boundaries without private chat history.

## Stage 1 — Deterministic session and OR reconstruction

Implement:

- timezone-aware session definitions using IANA zones;
- user-selected display timezone;
- DST-safe conversion;
- 40-minute Opening Range;
- OR High / OR Low;
- session-transition metadata.

Tests must include:

- Singapore session conversion;
- London summer/winter conversion;
- New York summer/winter conversion;
- OR high/low computation;
- no use of candles after the decision timestamp.

Exit condition:

The same timestamped candle stream deterministically produces the same session and OR state.

## Stage 2 — ACD level provider contract

Because A/C formulas are unknown, define an interface that accepts externally supplied:

- A Up;
- C Up;
- A Down;
- C Down;
- source identity/version;
- timestamp/effective-session metadata.

Reject malformed or temporally invalid levels.

Exit condition:

The strategy can consume real indicator levels without embedding an invented formula.

## Stage 3 — Previous-trend / market-structure representation

Represent:

- bullish;
- bearish;
- unclear;
- optionally unresolved strength.

First implementation should separate:

1. the strategy's required trend label;
2. the algorithm/provider used to obtain that label.

This lets manually annotated examples validate the strategy before a swing-detection algorithm is treated as canonical.

Exit condition:

Known annotated cases can be reproduced without mixing M1 noise into M15 previous-trend state.

## Stage 4 — Multi-timeframe setup state machine

Model the decision chain explicitly:

```text
SESSION_WAIT
-> OR_FORMING
-> OR_READY
-> WAITING_FOR_BOUNDARY
-> BOUNDARY_TOUCHED
-> WAITING_FOR_CONFIRMATION
-> CANDIDATE_READY
-> ACCEPTED | REJECTED | UNRESOLVED
```

Track:

- previous trend;
- M15 direction;
- M5 direction;
- M1 execution context;
- touched ACD boundary;
- momentum classification;
- confirmation mode/result.

Exit condition:

Every setup transition is auditable and cannot see future candles.

## Stage 5 — Structural stop, target and R:R gate

Implement the known contract:

- BUY stop below main structural invalidation low;
- SELL stop above main structural invalidation high;
- target comes from an externally supplied or later formalized meaningful structural/ACD target;
- minimum R:R = 1:2;
- below 1:2 = reject;
- exactly 1:2 = full exit at target;
- greater than 1:2 = partial at 2R, remainder rule unresolved.

Until structural-high/low and target-selection algorithms are canonical, allow annotated/provider-supplied values and record their source.

Exit condition:

No setup can be accepted without an explicit stop, target and valid R:R calculation.

## Stage 6 — Validation corpus

Collect annotated examples from the trader/course material.

Each example should ideally contain:

- instrument;
- session/date;
- chart timeframe(s);
- OR boundaries;
- A/C levels;
- previous trend;
- M15/M5 interpretation;
- momentum classification;
- confirmation candles;
- entry;
- main invalidation swing;
- target;
- take/skip decision;
- explanation.

Use examples to test fidelity, not to optimize for profit.

Exit condition:

The implementation matches a sufficiently varied set of human-labeled strategy examples, and mismatches are documented rather than silently patched.

## Stage 7 — Historical replay / backtest

After enough rules are deterministic:

- replay M1 data chronologically;
- derive/resample M5/M15 without future leakage;
- apply spread, commissions and conservative slippage;
- record all candidates, accepted trades and rejected trades;
- preserve strategy version and data version.

Core metrics:

- number of candidate setups;
- trade count;
- win rate;
- average win/loss in R;
- expectancy in R;
- profit factor;
- max drawdown;
- average holding time;
- results by instrument;
- results by session;
- results by trend alignment;
- results by momentum/confirmation class;
- cost sensitivity.

Do not optimize and evaluate on the same final sample.

## Stage 8 — Walk-forward / out-of-sample evaluation

Separate:

- development/tuning period;
- validation period;
- final unseen evaluation period.

Any change made after seeing evaluation results creates a new strategy version and requires new unseen evidence.

Exit condition:

The strategy either demonstrates stable positive expectancy after costs or is rejected/returned for new research.

## Stage 9 — Live paper/shadow trading

Run the frozen strategy against live data without real money.

Compare:

- theoretical signal time;
- data-arrival time;
- executable entry;
- spread/slippage;
- theoretical vs simulated realized R;
- missed/late signals;
- provider failures.

Exit condition:

Live paper behavior is close enough to historical assumptions to justify further work.

## Stage 10 — LLM augmentation experiment

Only after the deterministic baseline exists.

Candidate LLM roles may include:

- classifying ambiguous structure;
- classifying momentum quality;
- summarizing relevant news/context;
- adversarial critique of a candidate setup;
- explaining contradictory signals.

The LLM must be evaluated as an additive component against the deterministic baseline. It must not control position sizing, leverage, hard loss limits or kill switches.

## Stage 11 — Deterministic risk and tiny live validation

Not authorized by this v0.1 plan.

Before any live money:

- freeze position-sizing rules;
- freeze per-trade risk;
- freeze daily/portfolio loss limits;
- add execution guards and kill switch;
- demonstrate paper performance;
- explicitly authorize a tiny-capital live experiment.

## Versioning rule

Strategy rules, data assumptions and execution assumptions are part of the experiment version.

A material rule change creates a new version. We do not rewrite old results as though the new rule had always existed.