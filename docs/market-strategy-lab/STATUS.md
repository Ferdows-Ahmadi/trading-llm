# Market Strategy Lab Status

Snapshot date: 2026-09-14

## Current phase

```text
Stage 0 complete enough to collaborate
Stage 1 started: timezone-safe session engine
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
| Session definitions | Implemented |
| Timezone/DST conversion | Implemented |
| 40-minute OR window timing | Implemented |
| OR high/low from candles | Not started |
| External A/C level provider | Not started |
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

1. Keep CI green for the new package.
2. Implement chronological candle models and Opening Range high/low reconstruction.
3. Add tests proving OR computation uses only candles inside the 40-minute window.
4. Define the external A/C level provider contract without inventing the formula.
5. Begin an auditable session decision ledger.

## Research inputs still needed later

- exact A/C formula or authoritative indicator output format;
- exact ACD4 directional logic;
- trader-labeled examples of strong vs normal momentum;
- trader-labeled main structural highs/lows;
- confirmation examples;
- partial-close percentage and remainder management;
- canonical instrument/session list.
