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
Stage 7a: no-lookahead M1 -> M5/M15 replay primitives — implemented
Stage 7b: full historical replay + realistic cost model — next
```

## Current branch / PR

```text
branch: research/market-strategy-lab-v0.1
PR: #2 Market Strategy Lab v0.1: ACD research foundation (draft)
```

Latest verified Market Strategy Lab CI at this snapshot:

```text
run: 34877267941
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
| M1 chronological visibility | Implemented |
| M5/M15 no-lookahead resampling | Implemented with explicit grid anchor |
| Incomplete/duplicate higher-timeframe source rejection | Implemented |
| Full historical replay orchestrator | Not started |
| Cost model | Not started |
| Backtest | Not started |
| Walk-forward evaluation | Not started |
| Paper trading | Not started |
| LLM augmentation experiment | Deferred |
| Live execution | Not authorized |

## Replay safety now enforced

- M1 candles are visible only after the one-minute candle has closed;
- future M1 candles cannot change a prior replay snapshot;
- M5/M15 bars are emitted only after the entire higher-timeframe bar has closed;
- duplicate visible M1 timestamps are rejected;
- a partially missing closed higher-timeframe bucket is rejected instead of silently reconstructed;
- callers must supply the higher-timeframe grid anchor explicitly, so broker/session alignment is not guessed;
- OHLC is reconstructed from exact constituents and aggregate volume becomes unknown when source volume is incomplete.

## Trade-plan safety now enforced

- provider-supplied stop/target values carry source/version and observation/availability timestamps;
- BUY geometry must satisfy structural stop < entry < target;
- SELL geometry must satisfy target < entry < structural stop;
- future or wrong-session trade plans are rejected;
- R:R below 1:2 is rejected rather than repaired by moving the stop;
- exactly 1:2 maps to full exit at target;
- above 1:2 maps to partial exit at 2R while partial percentage and remainder exit remain explicitly unresolved;
- an `ACCEPTED` setup state cannot exist without a causally valid accepted trade plan meeting the 1:2 minimum.

## Immediate engineering frontier

1. Add an explicit cost model for spread, commission and conservative slippage without hard-coding one broker.
2. Build a chronological replay orchestrator that emits decision snapshots at known timestamps.
3. Connect session/OR, A/C provider, directional context, candidate-state ledger and trade-plan provider in replay.
4. Keep momentum and exact confirmation logic provider/annotation-supplied until the trader definitions are sufficiently precise.
5. Populate the validation corpus with real annotated examples before treating strategy fidelity as proven.

## Research inputs still needed later

- exact A/C formula or authoritative indicator output format;
- exact ACD4 directional logic;
- trader-labeled examples of strong vs normal momentum;
- trader-labeled main structural highs/lows;
- confirmation examples;
- partial-close percentage and remainder management;
- canonical instrument/session list.
