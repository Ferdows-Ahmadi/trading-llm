# ACD Fast Scalp v0.1

Status: **SOURCE-BASED FORMALIZATION**

This document records only the strategy rules currently supported by the supplied course notes, diagrams, and trader explanations. Missing details remain unresolved by design.

## 1. Session model

The strategy is organized around major regional openings:

- Asia represented by Singapore;
- Europe represented by London/Germany, with London as the current canonical opening reference;
- America represented by New York / the U.S. market.

Canonical home-time opening references currently supplied:

```text
Asia/Singapore     09:00 Asia/Singapore
Europe/London      08:00 Europe/London
America/New_York   09:30 America/New_York
```

The platform must convert those home-zone times into the user's selected timezone using timezone-aware rules. Do not hard-code seasonal offsets. London/New York daylight-saving changes must be handled by the timezone database.

## 2. Opening Range

Do not trade immediately on session open.

Use approximately the first **40 minutes** of the selected session to establish the Opening Range (OR).

Definitions:

- `OR_UP`: highest price reached during the OR;
- `OR_DOWN`: lowest price reached during the OR.

Only after the OR is complete are that session's ACD levels considered established for use.

## 3. ACD levels

Current level ordering, highest to lowest:

```text
C_UP
A_UP
OR_UP
OR_DOWN
A_DOWN
C_DOWN
```

Interpretation:

- `A_UP` / `C_UP`: upper resistance/boundary areas;
- `A_DOWN` / `C_DOWN`: lower support/boundary areas;
- `OR_UP` / `OR_DOWN`: central Opening Range boundaries.

**Important:** the exact formulas for A and C levels are not currently known.

v0.1 therefore treats A/C levels as externally supplied inputs from the existing indicator/tool. The implementation must not invent a formula.

## 4. Previous trend

"Previous trend" means the directional structure that existed immediately before the current OR/range formed.

Do not classify it from candles inside the current OR.

Use meaningful M15 structure before the range and ignore tiny M1 corrections unless larger structure has actually reversed.

### Bullish previous trend

Latest meaningful structure shows Higher Highs and Higher Lows.

Example:

```text
HL -> HH -> HL -> HH -> OR begins
```

Classification:

```text
BULLISH
```

### Bearish previous trend

Latest meaningful structure shows Lower Lows and Lower Highs.

Example:

```text
LH -> LL -> LH -> LL -> OR begins
```

Classification:

```text
BEARISH
```

### Unclear / range

If structure is mixed and does not show a clean HH/HL or LL/LH sequence, classify:

```text
UNCLEAR
```

Strong-vs-weak trend is conceptually recognized, but quantitative classification is not yet frozen.

## 5. Timeframe hierarchy

The strategy uses:

- M15: base direction / pressure;
- M5: confirmation/support of intended direction;
- M1: execution behavior only.

M1 must not independently override M15/M5 just because a brief correction appears.

## 6. Directional priority

When previous trend is bullish:

- preferred opportunity: BUY from lower ACD support (`A_DOWN` / `C_DOWN`);
- countertrend SELL at upper ACD levels is higher risk and is not the preferred baseline setup.

When previous trend is bearish:

- preferred opportunity: SELL from upper ACD resistance (`A_UP` / `C_UP`);
- countertrend BUY at lower levels is higher risk and is not the preferred baseline setup.

When previous trend is unclear:

- become more conservative;
- rely more heavily on M15/M5 direction and confirmation;
- exact acceptance rule remains unresolved.

## 7. Location rule

Primary BUY areas:

```text
A_DOWN
C_DOWN
```

Primary SELL areas:

```text
A_UP
C_UP
```

Do not force trades from the middle of the range.

A touch of an ACD level is **not** an entry by itself.

## 8. Momentum into the level

Before entry, classify how price approaches the relevant outer boundary.

Two conceptual states currently exist:

```text
NORMAL_OR_WEAK
STRONG_OPPOSING_MOMENTUM
```

A strong spike/momentum condition means price traverses a move dramatically faster than under normal conditions, for example a move that would commonly take much longer occurring within roughly a minute after a major news shock.

No numeric threshold is yet authorized.

Do not fight a strong spike simply because an ACD boundary was touched.

## 9. Confirmation

### Normal/weak opposing approach

Use approximately **one confirming candle**.

For a BUY, the confirming candle should react from lower support and close/reject meaningfully back above the area.

For a SELL, the confirming candle should reject upper resistance and close/separate meaningfully back below the area.

### Strong opposing momentum

Use approximately **three confirming candles** back through the relevant boundary before accepting that the level held.

Exact candle-shape and close-distance thresholds are unresolved.

## 10. BUY setup chain

Baseline BUY sequence:

```text
active session
-> wait ~40 minutes
-> OR complete
-> ACD levels available
-> previous trend preferably BULLISH
-> M15 supports bullish direction
-> M5 supports bullish direction
-> price reaches A_DOWN or C_DOWN
-> inspect M1 execution behavior
-> classify approach momentum
-> 1-candle or ~3-candle bullish confirmation
-> determine structural invalidation low
-> determine meaningful target
-> require R:R >= 1:2
-> BUY candidate accepted
```

## 11. SELL setup chain

Baseline SELL sequence:

```text
active session
-> wait ~40 minutes
-> OR complete
-> ACD levels available
-> previous trend preferably BEARISH
-> M15 supports bearish direction
-> M5 supports bearish direction
-> price reaches A_UP or C_UP
-> inspect M1 execution behavior
-> classify approach momentum
-> 1-candle or ~3-candle bearish confirmation
-> determine structural invalidation high
-> determine meaningful target
-> require R:R >= 1:2
-> SELL candidate accepted
```

## 12. Stop loss

Stop placement is structural, not a fixed number of pips/points.

### BUY

Place the stop below the **main low** whose break would invalidate the bullish setup.

Do not use every tiny M1 low.

### SELL

Place the stop above the **main high** whose break would invalidate the bearish setup.

Do not use every tiny M1 high.

If the correct structural stop creates unacceptable R:R, reject the trade instead of moving the stop artificially closer.

## 13. Targets and R:R

Potential targets may include:

- next meaningful ACD level;
- OR boundary;
- intermediate structural node;
- opposing support/resistance.

Exact target-priority logic is unresolved.

Minimum risk/reward:

```text
1:2
```

Rules currently supplied:

- if achievable R:R < 1:2 -> `REJECT`;
- if valid setup gives exactly 1:2 -> take the trade and close the full position at target;
- if available R:R exceeds 1:2 -> take partial profit at 2R and leave the remainder running.

The partial-close percentage and final remainder exit rule are unresolved.

## 14. Session transitions

When a newer major session opens, the new active session may take priority over older ACD structure.

Older levels may remain useful as targets, minor levels, or references.

Session overlap can increase liquidity and volatility but must not be interpreted automatically as easier trading.

## 15. Instrument scope

The strategy is described as applicable to markets including:

- forex pairs;
- gold;
- stocks / New York market instruments;
- other instruments whose activity is meaningfully linked to regional sessions.

Instrument-specific support is not yet validated. Each instrument/session combination must be evaluated rather than assumed equivalent.

## 16. v0.1 decision principle

The strategy is **not**:

```text
A_DOWN = BUY
A_UP = SELL
```

The current decision chain is:

```text
Session
-> Opening Range
-> ACD Levels
-> Previous Trend
-> M15/M5/M1 Direction
-> Outer Boundary
-> Momentum
-> Candle Confirmation
-> Entry
-> Structural Stop
-> Structural/ACD Target
-> R:R Gate
```

Any step that depends on a still-unresolved definition must return an explicit unresolved/indeterminate state instead of silently guessing.
