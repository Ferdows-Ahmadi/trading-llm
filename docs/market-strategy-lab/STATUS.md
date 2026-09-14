# Market Strategy Lab Status

Snapshot date: 2026-09-14

## Current phase

```text
Stage 0: collaboration/research boundaries — implemented
Stage 1: timezone-safe session + Opening Range reconstruction — implemented
Stage 2: external A/C level provider contract — implemented
Stage 3: previous-trend + M15/M5 directional context contract — implemented
Stage 4: auditable setup state machine / decision ledger — implemented
Stage 5: structural stop + target + R:R trade-plan contract — implemented
Stage 6: validation corpus format — implemented; corpus population pending
Stage 7: chronological historical replay infrastructure — next
```

## Current branch / PR

```text
branch: research/market-strategy-lab-v0.1
PR: #2 Market Strategy Lab v0.1: ACD research foundation (draft)
```

Latest verified Market Strategy Lab CI at this snapshot:

```text
run: 34877055710
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
| M1 setup state machine | Implemented as explicit immutable transitions |
| Momentum classifier | Qualitative states represented; quantitative classifier unresolved |
| Confirmation engine | States/modes represented; exact candle geometry unresolved |
| Structural stop selector | Provider/annotation contract implemented; deterministic selector unresolved |
| Target selector | Provider/annotation contract implemented; deterministic selector unresolved |
| R:R gate | Integrated: below 2R reject, exactly 2R full exit, above 2R partial-at-2R mode |
| Decision ledger | Implemented, versioned, append-only/immutable |
| Accepted-state trade-plan requirement | Implemented |
| Validation corpus | Machine-readable format/schema implemented; examples pending |
| Historical replay | Not started |
| M5/M15 no-lookahead resampling | Not started |
| Cost model | Not started |
| Backtest | Not started |
| Walk-forward evaluation | Not started |
| Paper trading | Not started |
| LLM augmentation experiment | Deferred |
| Live execution | Not authorized |

## Trade-plan safety now enforced

- provider-supplied stop/target values carry source/version and observation/availability timestamps;
- BUY geometry must satisfy structural stop < entry < target;
- SELL geometry must satisfy target < entry < structural stop;
- future or wrong-session trade plans are rejected;
- R:R below 1:2 is rejected rather than repaired by moving the stop;
- exactly 1:2 maps to full exit at target;
- above 1:2 maps to partial exit at 2R while partial percentage and remainder exit remain explicitly unresolved;
- an `ACCEPTED` setup state cannot exist without a causally valid accepted trade plan meeting the 1:2 minimum;
- duplicate entry/stop/target/R:R fields cannot conflict with the validated trade plan.

## Validation-corpus boundary

The canonical fidelity corpus has a documented JSON schema and example template. It records source provenance, OR/ACD values, trend/context labels, boundary, momentum, confirmation, intended entry/invalidation/target, take/skip/unresolved decision, explanation and unresolved fields.

Realized outcomes and later P/L are deliberately excluded from fidelity annotations so implementation matching is not confused with profit optimization.

## Immediate engineering frontier

1. Build chronological replay primitives around M1 candles.
2. Derive completed M5/M15 candles without future leakage.
3. Define explicit decision timestamps so only fully closed higher-timeframe candles are visible.
4. Connect session/OR, A/C provider, context provider and trade-plan provider into replay snapshots while unresolved momentum/confirmation rules remain externally supplied.
5. Add a realistic cost model before profitability claims or full backtests.

## Research inputs still needed later

- exact A/C formula or authoritative indicator output format;
- exact ACD4 directional logic;
- trader-labeled examples of strong vs normal momentum;
- trader-labeled main structural highs/lows;
- confirmation examples;
- partial-close percentage and remainder management;
- canonical instrument/session list.
