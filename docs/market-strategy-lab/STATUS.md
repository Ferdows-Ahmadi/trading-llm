# Market Strategy Lab Status

Snapshot date: 2026-09-14

## Current phase

```text
Stage 0: collaboration/research boundaries — implemented
Stage 1: timezone-safe session + Opening Range reconstruction — implemented
Stage 2: external A/C level provider contract — implemented
Stage 3: previous-trend + M15/M5 directional context contract — implemented
Stage 4: auditable setup state machine / decision ledger — implemented
Stage 5: structural stop + target + R:R trade-plan contract — next
Stage 6: validation corpus format — implemented; corpus population pending
```

## Current branch / PR

```text
branch: research/market-strategy-lab-v0.1
PR: #2 Market Strategy Lab v0.1: ACD research foundation (draft)
```

Latest verified Market Strategy Lab CI at this snapshot:

```text
run: 34876678494
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
| Structural stop selector | Partially specified; Stage 5 provider contract next |
| Target selector | Unresolved; Stage 5 provider contract next |
| R:R gate | Core 1:2 primitive implemented; Stage 5 integration next |
| Decision ledger | Implemented, versioned, append-only/immutable |
| Validation corpus | Machine-readable format/schema implemented; examples pending |
| Historical replay | Not started |
| Cost model | Not started |
| Backtest | Not started |
| Walk-forward evaluation | Not started |
| Paper trading | Not started |
| LLM augmentation experiment | Deferred |
| Live execution | Not authorized |

## State-machine safety now enforced

- legal setup transitions are explicit;
- every transition is immutable and timestamped;
- timestamps cannot move backward;
- post-session states cannot precede session opening;
- terminal accepted/rejected/unresolved states require explicit reasons;
- unresolved momentum/confirmation cannot silently become a ready candidate;
- terminal states cannot transition further;
- ledger serialization carries explicit schema and strategy versions.

## Validation-corpus boundary

The canonical fidelity corpus now has a documented JSON schema and example template. It records source provenance, OR/ACD values, trend/context labels, boundary, momentum, confirmation, intended entry/invalidation/target, take/skip/unresolved decision, explanation and unresolved fields.

Realized outcomes and later P/L are deliberately excluded from fidelity annotations so implementation matching is not confused with profit optimization.

## Immediate engineering frontier

1. Formalize provider-supplied structural invalidation and target values without inventing swing/target-selection algorithms.
2. Integrate deterministic BUY/SELL geometry and the 1:2 minimum R:R gate.
3. Represent exactly-2R full exit versus >2R partial-at-2R with remainder management explicitly unresolved.
4. Tighten `ACCEPTED` setup decisions so an accepted trade must have a validated trade plan.
5. Prepare chronological historical replay/resampling with no future-candle leakage.

## Research inputs still needed later

- exact A/C formula or authoritative indicator output format;
- exact ACD4 directional logic;
- trader-labeled examples of strong vs normal momentum;
- trader-labeled main structural highs/lows;
- confirmation examples;
- partial-close percentage and remainder management;
- canonical instrument/session list.
