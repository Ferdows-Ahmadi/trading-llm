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
Stage 7b: broker-agnostic execution cost model — implemented
Stage 7c: chronological replay snapshot orchestrator — implemented
Stage 8: boundary/confirmation integration + first historical experiment — next
```

## Current branch / PR

```text
branch: research/market-strategy-lab-v0.1
PR: #2 Market Strategy Lab v0.1: ACD research foundation (draft)
```

Latest verified Market Strategy Lab CI at this snapshot:

```text
run: 34877841775
result: success
checks: pytest + Ruff + mypy
```

The latest replay build ran 78 tests successfully before lint/type checks also passed.

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
| Execution cost assumptions | Versioned, broker-agnostic model implemented |
| Spread/slippage/commission P&L adjustment | Implemented for BUY and SELL |
| Replay phase model | Implemented: pre-session / OR-forming / post-OR |
| Replay snapshot orchestration | Implemented |
| Future provider snapshot isolation | Tested |
| Full strategy backtest | Not authorized yet; unresolved strategy rules remain |
| Walk-forward evaluation | Not started |
| Paper trading | Not started |
| LLM augmentation experiment | Deferred |
| Live execution | Not authorized |

## Replay orchestration now guarantees

- pre-session and OR-forming snapshots cannot expose the final Opening Range;
- future M1 candles cannot change a prior replay snapshot;
- future provider snapshots are ignored before the strategy is allowed to consume them;
- post-OR snapshots reconstruct the exact OR and then bind only causally available A/C levels, directional context and structural trade plans;
- M5 and M15 inputs remain closed-bar-only and use explicit caller-provided grid anchors;
- optional unresolved providers stay absent rather than being replaced with invented values.

## Cost-model boundary

- spread is an explicit full bid/ask spread assumption in basis points;
- entry and exit slippage are explicit adverse basis-point assumptions;
- commission is explicit per side;
- BUY and SELL receive directionally correct adverse execution prices;
- gross P/L, execution-price cost, commission cost, total cost and net P/L are all retained;
- assumptions carry a profile/version/source identity;
- the code intentionally contains no claim about which numerical cost assumptions are realistic for any broker or instrument.

## Immediate engineering frontier

1. Detect deterministic A/C boundary-touch events from visible post-OR M1 candles.
2. Add timestamped provider/annotation contracts for unresolved momentum and exact confirmation judgments.
3. Connect those events into the existing setup-state ledger without letting future candles rewrite earlier states.
4. Populate the validation corpus with real trader/course examples before claiming fidelity.
5. Freeze the first concrete historical experiment: instrument, data source, date range, session, bar alignment, cost profile, development/evaluation split.

## Research inputs still needed later

- exact A/C formula or authoritative indicator output format;
- exact ACD4 directional logic;
- trader-labeled examples of strong vs normal momentum;
- trader-labeled main structural highs/lows;
- confirmation examples;
- partial-close percentage and remainder management;
- canonical instrument/session list.
