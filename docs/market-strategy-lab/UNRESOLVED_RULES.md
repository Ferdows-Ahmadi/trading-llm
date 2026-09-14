# ACD v0.1 — Unresolved Rules

This file exists to prevent missing information from quietly turning into invented strategy logic.

A rule stays unresolved until it is supported by the trader/course material, a trusted indicator definition, or an explicitly versioned research decision.

## Critical unresolved definitions

### A/C level formulas

Unknown:

- exact formula for `A_UP`;
- exact formula for `A_DOWN`;
- exact formula for `C_UP`;
- exact formula for `C_DOWN`.

v0.1 handling:

- accept externally supplied A/C levels;
- record the level source/provider;
- never infer or reverse-engineer the formula from profitable examples and then pretend it was original strategy knowledge.

### ACD4 directional logic

Known:

- ACD4 is used to help assess short-term directional pressure;
- it references MA 15 / MA 30 / MA 60.

Unknown:

- SMA vs EMA or another MA type;
- input price;
- exact crossover/order/angle logic;
- exact bullish/bearish/neutral thresholds.

v0.1 handling:

- use an interface for directional context;
- allow externally supplied labels where needed;
- do not invent a moving-average rule.

### Meaningful swing detection

Known:

- previous trend should use meaningful structure, mainly on M15;
- tiny M1 noise should not redefine trend;
- bullish structure uses HH + HL;
- bearish structure uses LL + LH.

Unknown:

- exact pivot/swing algorithm;
- minimum bars between pivots;
- minimum price excursion;
- tie handling;
- reversal threshold.

### Strong vs weak trend

Known conceptually:

- strong trend has cleaner structure, less overlap and stronger directional movement;
- weak trend has deeper corrections / more overlap.

Unknown:

- quantitative threshold;
- whether trend strength changes entry permission or only priority/risk assessment.

### Strong momentum / spike

Known conceptually:

- price moves unusually far unusually quickly, often around major news;
- strong opposing momentum requires more confirmation and should not be fought automatically.

Unknown:

- ATR threshold;
- velocity threshold;
- candle-body threshold;
- volume requirement;
- exact lookback window.

No numeric threshold is authorized yet.

### Candle confirmation

Known:

- normal/weak approach may use one confirming candle;
- strong opposing approach uses approximately three confirming candles;
- confirmation should show rejection and movement back through/away from the relevant level.

Unknown:

- exact body/wick requirements;
- minimum close distance from the level;
- whether entry occurs at confirmation close or next-candle open;
- whether three candles must all close in the intended direction or only confirm cumulatively.

### Structural stop selection

Known:

- BUY stop below the main invalidation low;
- SELL stop above the main invalidation high;
- ignore tiny M1 swings;
- do not tighten a valid structural stop merely to force acceptable R:R.

Unknown:

- exact algorithm for choosing the main high/low when several plausible swings exist;
- buffer/spread treatment around the structural level.

### Target hierarchy

Known possible targets:

- OR level;
- ACD level;
- structural node;
- opposing support/resistance.

Unknown:

- deterministic priority/order;
- whether target is selected before or after entry confirmation;
- whether target may move while trade is open.

### Partial profit management

Known:

- exactly 1:2 -> close full position at target;
- if available R:R exceeds 1:2 -> partially close at 2R and leave a remainder.

Unknown:

- percentage closed at 2R;
- remainder stop management;
- remainder target;
- trailing-stop rule;
- session-end handling.

### Position sizing / account risk

Unknown:

- percentage of equity risked per trade;
- daily loss cap;
- simultaneous-position limit;
- correlated-exposure limits.

No live-risk rule is authorized in v0.1.

### Countertrend setups

Known:

- previous trend gives directional priority;
- countertrend trades are described as higher risk;
- unclear trend requires greater conservatism.

Unknown:

- whether countertrend setups are permitted in the baseline automated strategy;
- extra conditions if permitted.

Initial research default should be conservative and keep them separate from trend-aligned baseline statistics unless explicitly specified later.

### Instruments and sessions

Known broadly:

- forex, gold, stocks/indices and session-sensitive instruments are mentioned.

Unknown:

- canonical instrument list;
- which regional session is valid/preferred for each instrument/pair;
- whether the same parameters apply across all instruments.

### News handling

Known:

- large news can create spike/strong momentum conditions.

Unknown:

- whether a news calendar is part of the original strategy;
- whether major-news windows are hard no-trade periods;
- exact event classifications and exclusion windows.

## Rule for implementation

When code reaches one of these unresolved decisions, it must do one of the following:

1. consume an explicitly supplied value/label;
2. return `UNRESOLVED` / `INDETERMINATE`;
3. exclude the case from a specific experiment under a preregistered rule.

It must not choose an undocumented threshold simply because one makes the backtest prettier.