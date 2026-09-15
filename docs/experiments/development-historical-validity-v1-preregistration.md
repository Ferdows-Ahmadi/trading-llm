# Development historical-validity audit v1 preregistration

Status: preregistered before inspecting the full canonical development rows for this audit, before deriving the fresh validation cohort, and before any `market-residual-v2` scientific run.

This document defines the next research gate after the completed exploratory v0.5 pilot and the engineering-only integrity remediation at commit `554d5e18cf4d0e357dcd3ac6a46bd46a97f64c35`.

## Purpose

The immediate question is not whether a new forecaster beats the market. The immediate question is whether the historical development cases we would use for a fresh validation actually represent contracts whose wording, resolution semantics, outcome timing, and final labels can be defended at the historical forecast timestamp.

This stage therefore performs **no forecasting experiment and no model comparison**. It creates a fresh, development-only, event-disjoint candidate cohort and audits historical validity before any new forecasting method is authorized on those cases.

## Hard exclusions and custody

- Reserved holdout rows are out of scope. Their contents must not be inspected, selected, audited, scored, or exposed by this stage.
- `market-residual-v2` remains inactive. No LLM inference is authorized by this preregistration.
- No outcome, market probability, prior model forecast, v0.3/v0.4/v0.5 per-case score, evidence-bearing status, or later research result may influence candidate selection.
- The repeatedly inspected 20-question pilot is excluded at its **parent-event** level, not merely by question ID.
- `main` remains untouched; work stays on `research/prediction-market-lab-v0.1`.

The canonical source benchmark is the successful `First Polymarket Benchmark` run `34467576128`, source commit `7a2ef17b12bb7ede33bae7863532e7b408ce38be`, artifact `polymarket-public-benchmark-v0.1-clean`, artifact ID `10148227264`, artifact digest `sha256:5d347520903527abfa00dfa2618d44f1b709b849d5bca731dae61bc524e61ebb`.

Only the canonical development member is authorized for this stage. Its known manifest identity is:

- development rows: `255`
- development event groups: `84`
- development CSV SHA256: `c05cbfa404804789faec779877c839b6655abc317217f182a673b2e91bd9f9a7`
- forecast range: `2025-10-16T06:16:33+00:00` through `2026-04-15T20:01:06+00:00`

If a development-only derivative must be created from the combined historical artifact, the extraction process may read the archive directory and decompress/read **only** `development.csv` and `development.manifest.json`. It must verify the development SHA256 above, must not decompress/read any `holdout*` member or raw combined source record, must not print archive member contents, and must delete the transport archive after producing the verified development-only derivative. All later stages must use the development-only derivative rather than the combined artifact.

## Frozen pilot event exclusion set

The following parent event IDs were used in the repeatedly inspected 20-question pilot and are excluded from every fresh candidate in this audit and the subsequent validation derived from it:

```text
polymarket-event:57370
polymarket-event:96761
polymarket-event:84910
polymarket-event:84066
polymarket-event:131190
polymarket-event:147521
polymarket-event:159929
polymarket-event:161872
polymarket-event:89583
polymarket-event:189755
polymarket-event:89519
polymarket-event:153927
polymarket-event:192882
polymarket-event:217185
polymarket-event:127101
polymarket-event:133755
polymarket-event:181347
polymarket-event:73835
polymarket-event:230200
polymarket-event:84921
```

The exclusion set is fixed here before candidate derivation. It may not be edited because of audit outcomes or future forecast performance.

## Fresh candidate derivation

Starting from the verified 255-row canonical development dataset:

1. Require `split == development` for every row and exact dataset hash verification.
2. Remove every row whose `event_id` is in the frozen pilot exclusion set above.
3. Use only `question_id`, `question_text`, `forecasted_at`, `source_cutoff_at`, `event_id`, and `category` for candidate derivation. Outcome, market probability, resolution time, and prior forecast/evidence fields are forbidden inputs to selection.
4. Sort remaining rows by `forecasted_at`, then `question_id` ascending.
5. Keep the first row for each distinct `event_id`.
6. Keep **all** resulting event representatives. There is no target count and no discretionary replacement of inconvenient questions.
7. Freeze the candidate table and manifest before beginning historical-validity adjudication.

If a pilot event ID is absent from the canonical development dataset, if a candidate has a blank event ID, or if the verified source hash differs, derivation fails instead of silently changing the cohort.

This produces one representative per previously uninspected development parent event and prevents sibling questions from making the apparent sample larger than the parent-event count.

## Historical-validity audit model

Every frozen candidate receives three independent required checks. The adjudicator may inspect historical contract/settlement sources, but must not inspect any LLM forecast, forecast correctness, residual action, or per-case model-versus-market score for the candidate.

Each required check has one of `verified`, `contradicted`, or `unknown` status. Evidence references and timestamps must be persisted.

### A. Contract identity as of forecast time

Goal: establish that the benchmark question is the same historical contract the market participants faced at the forecast cutoff.

A candidate is `verified` only if a timestamped Polymarket-origin or independently archived snapshot available at or before `forecasted_at` provides enough contract metadata to identify the exact market and its question. The normalized historical question text must equal the frozen benchmark `question_text`. Normalization is limited to Unicode normalization, line-ending normalization, trimming, and collapsing runs of whitespace. Semantic paraphrase is not accepted as equality.

The audit must also preserve any historical description, resolution criteria, and resolution-source locator available in that snapshot. Absence of a pre-cutoff snapshot sufficient to establish the contract is `unknown`, not assumed valid.

A pre-cutoff snapshot proving that the benchmark question text had materially different wording is `contradicted`.

Current/post-resolution Polymarket metadata may be used only as a locator for archives or official sources. It cannot by itself satisfy this as-of requirement.

### B. Outcome unknowability at forecast time

Goal: establish that the proposition had not already become objectively decided by `forecasted_at`, regardless of when Polymarket later marked the market closed.

The audit must identify the contract's decisive real-world event or deadline from the historical resolution terms and obtain timestamped authoritative evidence for when the decisive fact became knowable.

- `verified`: authoritative evidence places the decisive event/fact strictly after `forecasted_at`.
- `contradicted`: authoritative evidence places the decisive event/fact at or before `forecasted_at`.
- `unknown`: the decisive boundary cannot be established with adequate timestamped evidence.

`closedTime > forecasted_at` is never sufficient by itself.

### C. Authoritative final label

Goal: verify the benchmark label independently of terminal `outcomePrices`.

The audit must obtain a Polymarket resolution record tied to the resolution mechanism or another authoritative source specified by the historical contract. It records `authoritative_outcome` as binary Yes/No only when the source supports it.

- `verified`: independently supported final label equals the canonical benchmark label.
- `contradicted`: independently supported final label disagrees with the canonical benchmark label.
- `unknown`: no adequate authoritative final label can be established.

Terminal near-1/0 market prices are not authoritative evidence for this check.

## Overall historical-validity classification

For each candidate:

- `verified_valid` only if A, B, and C are all `verified`.
- `invalid` if any of A, B, or C is `contradicted`.
- `unknown` otherwise.

`unknown` is not silently promoted to valid and is not scored in the future fresh validation.

The audit may not create ad hoc exceptions after seeing which cases pass. Any change to these rules requires a new version and cannot retroactively alter this v1 result.

## Retrospective-schedule limitation

The canonical benchmark chooses a trade near `actual closedTime - 7 days`, then uses that trade timestamp as forecast/evidence cutoff. This is a retrospective evaluation schedule because actual closure time is known only after the fact.

Passing this audit therefore establishes historical internal validity for the benchmark; it does **not** establish that the same forecast schedule was prospectively executable. Every audit artifact must carry `retrospective_close_anchored_schedule: true`. A later deployment study must define a prospective trigger independently.

## Audit artifact

The frozen audit output must contain at least:

- candidate identity and event ID
- forecast timestamp and source cutoff
- normalized frozen question hash
- contract check status, evidence locator(s), capture/publication timestamp(s), and historical question hash
- historical description/resolution-rules hash when available
- outcome-unknowability status, decisive-event timestamp when established, source locator, and source timestamp
- authoritative-label status, authoritative outcome when established, source locator, and source timestamp
- overall classification
- machine-readable reason code(s)
- `retrospective_close_anchored_schedule: true`
- code commit and candidate dataset hash

The artifact must include all candidates, including invalid and unknown cases. Failures cannot disappear from the denominator.

## Stage exit

This stage ends after the full candidate audit is frozen and summarized. It does **not** run a forecaster.

The next stage may use only `verified_valid` candidates to design a fresh development-validation experiment. The number of verified-valid cases and their dependency/time structure may be used to choose an appropriate preregistered uncertainty analysis and to decide that the available development sample is inadequate. Model forecasts/results on these candidates must remain unseen until that separate validation preregistration is committed.

No result from this historical-validity audit authorizes opening the reserved holdout.
