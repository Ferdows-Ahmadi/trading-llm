# Market Strategy Lab Status

Snapshot date: 2026-09-14

## Current phase

```text
Stage 0: collaboration/research boundaries — implemented
Stage 1: timezone-safe session + Opening Range reconstruction — implemented
Stage 2: external A/C level provider contract — implemented
Stage 3: previous-trend + M15/M5 directional context contract — implemented
Stage 4: auditable setup state machine / decision ledger — next
```

## Current branch / PR

```text
branch: research/market-strategy-lab-v0.1
PR: #2 Market Strategy Lab v0.1: ACD research foundation (draft)
```

Latest verified Market Strategy Lab CI at this snapshot:

```text
run: 34876280799
result: success
checks: pytest + Ruff + mypy
```

## Module status

| Component | Status |
| --- | --- |
| Collaborator onboarding | Implemented |
| Market Strategy Lab charter | Implemented |
| ACD v0.1 source specification | Implemented |
| Unresolved-rule register | Implemented |
| Experiment roadmap | Implemented |
| Strategy package scaffold | Implemented |
| Dedicated CI | Green |
| Session definitions | Implemented |
| Timezone/DST conversion | Implemented |
| 40-minute OR window timing | Implemented |
| Timezone-aware M1 candle model | Implemented |
| OR high/low from candles | Implemented |
| Missing/duplicate OR candle rejection | Implemented |
| Future/outside-OR candle exclusion | Tested |
| External A/C level provider | Contract implemented; exact formula unresolved |
| Previous-trend provider/algorithm | Provider/annotation contract implemented; deterministic swing algorithm unresolved |
| M15/M5 direction contract | Implemented with timestamp/no-lookahead validation |
| M1 setup state machine | Not started |
| Momentum classifier | Unresolved / not started |
| Confirmation engine | Partially specified, not started |
| Structural stop selector | Partially specified, not started |
| Target selector | Unresolved / not started |
| R:R gate | Core 1:2 primitive implemented |
| Decision ledger | Not started |
| Validation corpus | Not started |
| Historical replay | Not started |
| Cost model | Not started |
| Backtest | Not started |
| Walk-forward evaluation | Not started |
| Paper trading | Not started |
| LLM augmentation experiment | Deferred |
| Live execution | Not authorized |

## Directional-context safety now enforced

- previous-trend observations cannot extend into the current Opening Range;
- M15/M5 observations are timestamped independently;
- context snapshots carry source/version identity;
- snapshots cannot be used before their latest observation exists;
- snapshots from the future are rejected at decision time;
- session identity and session-open instant must match;
- M1 is intentionally excluded from the directional-bias contract.

## Immediate engineering frontier

1. Build the auditable ACD setup state machine and decision ledger (#4).
2. Define the annotated trader-validation corpus format (#5).
3. Keep unresolved momentum, confirmation, structural-stop and target logic explicit rather than fabricating thresholds.
4. Connect OR + A/C levels + directional context into deterministic candidate-state transitions.
5. Prepare the historical replay boundary without future-candle leakage.

## Research inputs still needed later

- exact A/C formula or authoritative indicator output format;
- exact ACD4 directional logic;
- trader-labeled examples of strong vs normal momentum;
- trader-labeled main structural highs/lows;
- confirmation examples;
- partial-close percentage and remainder management;
- canonical instrument/session list.
