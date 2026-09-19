# Prospective Live Source Routing v0.4 — Design Draft

Status: **design draft only**. No v0.4 market selection, evidence acquisition, model inference, outcome lookup, or reserved-holdout access is authorized by this document.

Experiment ID: `prospective-live-source-routing-v0.4`

## Purpose

Repeat the v0.3 paired evidence experiment on a fresh prospective cohort after fixing the adapter-state collision discovered in v0.3.

The scientific comparison remains:

- Condition A: exact-question Google News RSS baseline.
- Condition B: the same frozen RSS evidence plus successfully retrieved contract resolution-source material.

The market prior, frozen local model identities, residual mapping, prompt family, and acquisition ordering should remain as close as practical to v0.3 so the development question remains focused on evidence quality.

## Required implementation correction

Each model-condition pair must own an independent residual-adapter decision namespace.

Acceptable implementation:

- create one adapter for Llama Condition A and a separate adapter for Llama Condition B;
- same for Qwen;
- same for DeepSeek.

Equivalent isolation is acceptable only if tests prove that the same market `question_id` can be forecast once under Condition A and once under Condition B without sharing decision-record state.

Do not alter the frozen v0.3 artifacts or rerun v0.3.

## Success accounting correction

v0.4 must distinguish:

1. **terminal safety**: every forecast-ready cell ends in a protocol-recognized terminal state;
2. **paired inference success**: for every evidence-bearing A/B cell, the intended model request completes and yields `model_evaluated`; verified-empty conditions may use deterministic no-op without a model call.

A run with systematic `model_failure_noop` records may be terminally safe but must not be labeled a successful paired inference experiment.

The summary should expose both booleans explicitly.

## Regression tests required before protocol freeze

At minimum:

- same model + same `question_id` can run Condition A and Condition B independently;
- Condition A adapter state cannot contaminate Condition B;
- all three models produce independent A/B decision accounting;
- verified-empty A with evidence-bearing B behaves correctly;
- evidence-bearing A with evidence-bearing B behaves correctly;
- one model-condition failure does not overwrite another cell;
- paired inference success is false if any intended evidence-bearing model call ends in `model_failure_noop`;
- no-overwrite/no-retry behavior remains enforced.

## Prospective boundaries

Use a fresh cohort and fresh selection seed.

Do not reuse v0.3 markets merely to recover the failed B forecasts. Do not use v0.3 outcomes for tuning before v0.4 forecasts freeze.

The reserved historical holdout remains untouched.

A fresh local model identity freeze and a final preregistration are required before the first v0.4 market-universe query.
