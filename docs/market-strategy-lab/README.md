# Market Strategy Lab

## Purpose

The Market Strategy Lab is the second major research lane in `trading-llm`.

Its job is to convert human trading methods into explicit, testable strategy specifications, evaluate them on historical and then live paper data, and only later allow them to approach real execution.

This lab is separate from the Prediction Market Lab. They share the same long-term autonomous-trading mission, but they must not contaminate each other's experiments.

## Strategy 001

The first strategy is **ACD Fast Scalp v0.1**.

Current phase:

```text
FORMALIZATION / RESEARCH SCAFFOLD
```

Current objective:

> Given historical market data, session configuration, and externally supplied ACD levels, reconstruct what the strategy would have known at each moment, identify candidate setups under the rules we actually know, reject invalid/underspecified cases, and emit a complete auditable decision ledger.

## What success means now

For the current milestone, success does **not** mean profit.

Success means:

- the same data + same strategy version produce the same decision;
- timestamps and sessions are timezone/DST safe;
- no future candle is used to make a past decision;
- known rules are implemented faithfully;
- unknown rules are surfaced explicitly rather than guessed;
- every accepted or rejected setup has a reason;
- risk/reward is computed before a trade is considered valid;
- historical replay is reproducible.

## Current strategy knowledge

Known at v0.1:

- sessions: Asia/Singapore, Europe/London, America/New York;
- use the first approximately 40 minutes as the Opening Range (OR);
- OR High is the highest price during the OR;
- OR Low is the lowest price during the OR;
- ACD levels are ordered `C Up > A Up > OR Up > OR Down > A Down > C Down`;
- A/C level formulas are not yet known and must be supplied externally for v0.1;
- previous trend is determined from meaningful structure before the current OR, primarily on M15;
- bullish structure uses Higher High + Higher Low;
- bearish structure uses Lower Low + Lower High;
- unclear structure remains `UNCLEAR`;
- M15 is the base directional timeframe;
- M5 confirms/supports direction;
- M1 is for execution behavior, not standalone bias;
- BUY candidates are mainly at A Down / C Down;
- SELL candidates are mainly at A Up / C Up;
- do not trade the middle merely because an ACD line exists;
- normal approach may use one-candle confirmation;
- strong opposing momentum/spike uses approximately three confirming candles;
- BUY stop belongs below the main structural invalidation low;
- SELL stop belongs above the main structural invalidation high;
- minimum accepted risk/reward is 1:2;
- if valid R:R is below 1:2, reject the trade;
- at exactly 1:2, close the full position at target;
- above 1:2, take partial profit at 2R and leave a remainder according to a still-unresolved exit rule;
- a newly active major session can supersede older-session ACD priority;
- supported markets may include forex, gold, stocks/indices and other session-sensitive instruments, subject to later instrument-specific validation.

## Intended architecture

```text
Market data
    |
Normalization / timeframes / timezone handling
    |
Session engine + Opening Range
    |
ACD level provider
    |
Market structure / previous trend
    |
M15 -> M5 -> M1 context
    |
Momentum + confirmation
    |
Candidate entry
    |
Structural stop + target + R:R gate
    |
Decision ledger
    |
Historical replay / backtest
    |
Paper trading
    |
LLM augmentation experiment
    |
Deterministic risk / execution
    |
Tiny live-capital validation (only if authorized later)
```

## Repository layout

The strategy-specific package will live under:

```text
packages/strategy-lab/
```

Generic backtesting capability should remain in `packages/backtest/` rather than becoming ACD-specific.

## Rule for unknowns

Unknown strategy details are part of the scientific state of the project.

Do not replace an unknown with a convenient threshold. Use an interface, an `UNRESOLVED` state, or an externally supplied value until the rule is sourced and versioned.
