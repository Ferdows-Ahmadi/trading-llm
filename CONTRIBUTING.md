# Contributing to trading-llm

This repository contains research code. A contribution can change experimental meaning even when the diff looks small, so code review must cover both software correctness and research validity.

## Start here

For Market Strategy Lab work, read:

1. `docs/COLLABORATOR_ONBOARDING.md`
2. `docs/market-strategy-lab/README.md`
3. `docs/market-strategy-lab/ACD_FAST_SCALP_V0.1.md`
4. `docs/market-strategy-lab/UNRESOLVED_RULES.md`
5. `docs/market-strategy-lab/EXPERIMENT_PLAN.md`

## Branches

Do not push feature work directly to `main`.

Market Strategy Lab integration branch:

```text
research/market-strategy-lab-v0.1
```

Create focused feature branches from that branch and open pull requests back into it.

Examples:

```text
feat/acd-opening-range
feat/acd-level-provider
feat/acd-structure-labels
test/acd-validation-corpus
fix/session-dst
```

Prediction Market Lab has its own research branch and its own scientific boundaries. Do not mix the two lanes in one PR.

## Pull request expectations

A useful PR should state:

- what problem it solves;
- which strategy/research rule it implements;
- whether it changes scientific semantics or only implementation;
- assumptions introduced;
- unresolved questions;
- tests added/changed;
- whether historical/live results were inspected before making the change.

If a change alters a trading rule, threshold, target, stop, data-selection rule or evaluation method, treat it as a research-method change and document/version it accordingly.

## Quality checks

For `packages/strategy-lab`:

```bash
python -m pip install -e "packages/strategy-lab[dev]"
pytest packages/strategy-lab/tests -q
ruff check packages/strategy-lab
mypy packages/strategy-lab/src
```

All checks should pass before merge.

## Strategy knowledge rule

Do not invent missing ACD definitions.

An unresolved rule should remain an interface, supplied annotation, or explicit `UNRESOLVED` state until sourced and versioned.

## Backtest integrity

- Replay chronologically.
- Never use future candles to make a past decision.
- Include realistic costs before profitability claims.
- Keep development/tuning data separate from final evaluation data.
- A rule changed after seeing evaluation results creates a new strategy version.
- Preserve losing and rejected cases. They are data, not clutter.

## Live trading

Live execution is not authorized by the Market Strategy Lab v0.1 branch.

Do not add credentials, exchange balances, broker-order calls or hidden auto-execution paths without an explicitly reviewed later-stage design.

## Secrets

Never commit API keys, broker credentials, passwords, wallet seeds or private tokens.
