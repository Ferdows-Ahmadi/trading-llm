# Prospective clustered evidence v0.1 retirement

Status: **retired for infrastructure failure; no scientific efficacy conclusion authorized.**

Effective date: 2026-09-15.

This document closes the GDELT -> Common Crawl historical-reconstruction evidence lane that was intended to support the frozen 77-market prospective development cohort. The underlying market-custody artifact remains valid as an immutable record of the selected markets, but the evidence-acquisition design is no longer authorized for further recovery attempts.

## Why the lane is retired

The evidence method was attempted through three escalating execution designs:

1. the original single-run acquisition;
2. transport recovery v1 with deterministic sharding and retries;
3. transport recovery v2 with slower provider pacing, longer timeouts, stronger retry policies, deterministic staggering, and reduced concurrency.

Across these attempts, no verified terminal evidence row was produced. Failures were dominated by upstream transport/provider behavior including GDELT HTTP 429 responses and malformed payloads, plus Common Crawl disconnects, timeouts, HTTP 503 responses, and other lookup failures. GitHub Actions also imposed a six-hour wall-clock boundary on long-running shards, but the rows that completed before cancellation still ended as `retrieval_failure`.

The failure therefore is classified as an **architecture/infrastructure mismatch**, not evidence that the forecaster lacks predictive value.

## Canonical historical record

The following artifacts and runs remain immutable research history:

- canonical 77-market v0.3 custody artifact;
- original prospective evidence run and its partial artifact;
- recovery v1 artifacts;
- recovery v2 artifacts and logs;
- all frozen preregistrations, schema clarifications, recovery amendments, code commits, receipts, hashes, and checkpoints.

No artifact is deleted or rewritten to hide the failed path.

## Retirement boundary

After this retirement commit:

- no recovery v3 is authorized;
- no new GDELT/Common Crawl request may be made for this 77-market evidence lane;
- no substitute evidence source may be injected into the frozen 77-market cohort;
- any v2 job that was already running at retirement time may finish or be cancelled by its execution environment, but its output is archival only and cannot reopen the lane;
- no LLM forecast may be produced from incomplete/retrieval-failure evidence for this cohort;
- no outcomes, post-cutoff prices, or reserved holdout data may be inspected to decide whether to revive this cohort.

The 77-market cohort is therefore **closed without a forecaster evaluation**.

## What is preserved for the next experiment

The following design elements remain sound and may be reused prospectively:

- deterministic market selection and immutable custody;
- event-aware sampling and clustering discipline;
- frozen market probability as the comparator;
- frozen Llama 3.1 8B Instruct model identity;
- fixed residual-logit adjustment bands;
- immutable evidence hashing and raw-source custody;
- explicit `verified_complete`, `verified_empty`, and `retrieval_failure` semantics;
- outcome blindness;
- event-balanced paired Brier and log-loss evaluation;
- reserved-holdout boundary.

The historical reconstruction layer itself is not carried forward.

## Replacement direction

A new, separately preregistered experiment will capture evidence **live at forecast time**. Evidence is frozen first, the market comparator snapshot is taken immediately afterward, and the model forecast is then frozen. This ensures the model never receives evidence newer than the market snapshot.

The new experiment is not an amendment to this retired lane. It is a new prospective pilot with a new cohort, new evidence protocol, and separate artifacts.
