# AGENTS.md

Guidance for coding agents working in this repository branch.

## Active lane

This branch is for:

```text
research/market-strategy-lab-v0.1
```

Primary package:

```text
packages/strategy-lab/
```

Primary strategy:

```text
ACD Fast Scalp v0.1
```

## Read before editing

- `docs/COLLABORATOR_ONBOARDING.md`
- `docs/market-strategy-lab/README.md`
- `docs/market-strategy-lab/ACD_FAST_SCALP_V0.1.md`
- `docs/market-strategy-lab/UNRESOLVED_RULES.md`
- `docs/market-strategy-lab/EXPERIMENT_PLAN.md`

## Scientific guardrails

Do not:

- invent A/C formulas;
- invent ACD4 logic;
- invent momentum thresholds;
- invent structural-swing thresholds;
- silently enable countertrend trades;
- tune rules on final evaluation data;
- use future candles during historical decisions;
- add live order execution;
- modify Prediction Market Lab experimental artifacts from this branch;
- inspect Prediction Market Lab protected holdout/outcomes for adaptation.

Unknown strategy details must remain explicit unresolved states or externally supplied inputs.

## Engineering rules

- Keep timestamps timezone-aware.
- Prefer IANA timezones and `zoneinfo`.
- Keep strategy-specific logic in `packages/strategy-lab`.
- Keep generic replay/backtest infrastructure reusable in `packages/backtest`.
- Add tests for every deterministic rule.
- Preserve auditability: accepted and rejected decisions need reasons.
- Use strong typing.
- Do not commit secrets.

## Required checks

```bash
python -m pip install -e "packages/strategy-lab[dev]"
pytest packages/strategy-lab/tests -q
ruff check packages/strategy-lab
mypy packages/strategy-lab/src
```

## Research principle

> Prove information -> prove tradability -> prove execution -> risk tiny money -> scale evidence, not confidence.
