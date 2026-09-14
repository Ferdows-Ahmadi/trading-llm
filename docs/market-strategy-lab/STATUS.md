# Market Strategy Lab Status

Snapshot date: 2026-09-14

## Current phase

```text
Stage 0: collaboration/research boundaries — implemented
Stage 1: timezone-safe session + Opening Range reconstruction — implemented
Stage 2: external A/C level provider contract — implemented
Stage 3: previous-trend / directional-context boundary — next
```

## Current branch / PR

```text
branch: research/market-strategy-lab-v0.1
PR: #2 Market Strategy Lab v0.1: ACD research foundation (draft)
```

Latest verified Market Strategy Lab CI at this snapshot:

```text
run: 34874865207
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
| External A/C level snapshot model | Implemented |
| External A/C provider interface | Implemented |
| A/C source/version identity | Implemented |
| A/C temporal anti-lookahead checks | Implemented |
| A/C-to-OR ordering validation | Implemented |
| Previous-trend provider/algorithm | Not started |
| M15/M5 direction contract | Not started |
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

## Immediate engineering frontier

1. Define previous-trend and M15/M5 directional-context provider boundaries so trader annotations can be consumed before any swing algorithm or ACD4 formula is treated as canonical.
2. Start the auditable decision ledger/state-machine model.
3. Define the annotated validation-corpus format for examples from the trader/course.
4. Add a conservative trend-aligned baseline path while leaving countertrend permission unresolved.
5. Preserve all unknown momentum/confirmation/stop-selection definitions as explicit unresolved states until sourced.

## Research inputs still needed later

- exact A/C formula or authoritative indicator output format;
- exact ACD4 directional logic;
- trader-labeled examples of strong vs normal momentum;
- trader-labeled main structural highs/lows;
- confirmation examples;
- partial-close percentage and remainder management;
- canonical instrument/session list.
