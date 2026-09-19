# Historical-validity adjudication v1 protocol

Status: preregistered before reading canonical development outcome labels for the fresh 64-candidate cohort and before performing any new public-web source search for decisive-event or authoritative-label evidence.

This protocol operationalizes the already-preregistered A/B/C audit in `development-historical-validity-v1-preregistration.md`. It does not authorize forecasting, model inference, market-residual-v2, holdout access, or any model-versus-market scoring.

## Frozen parent identities

Candidate cohort:

- candidate artifact: `historical-validity-candidates-v0.1`
- candidate workflow run: `34738563200`
- candidate artifact ID: `10312295819`
- candidate artifact archive digest: `sha256:dc19595f7c59e8ddf9787c9a24530c9b32eedcccffedb1040754e4b0a48780af`
- candidate CSV SHA256: `6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21`
- candidate rows / parent events: `64 / 64`

Canonical historical source-discovery artifact:

- workflow run: `34767754110`
- artifact: `historical-validity-source-discovery-v0.2-canonical`
- artifact ID: `10320984640`
- artifact archive digest: `sha256:aee2e398b421bd8b2a94fbfd3f5edf2c6fb28c2b71f490e8a98c60ee3b8c7648`
- source-discovery acquisition-code commit: `70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2`
- source-discovery candidate SHA256: `6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21`
- lookup rows: `384`
- frozen pre-cutoff captures: `3`
- questions with frozen capture: `3`
- exact historical-question-match diagnostics: `3`

The source-discovery artifact was produced through deterministic execution recovery after one original 16-row shard timed out. Recovery provenance is part of the canonical artifact. This execution history does not alter the source-discovery protocol or candidate membership.

## Audit scope and hard exclusions

All 64 frozen candidates remain in the audit denominator.

Forbidden inputs to adjudication include:

- any LLM forecast for these candidates;
- any residual action or model confidence;
- any model-versus-market score;
- any v0.3/v0.4/v0.5 case-level result;
- any reserved-holdout content;
- terminal market prices as authoritative outcome evidence.

Current/post-resolution Polymarket metadata remains locator-only. It may help identify official sources or market identifiers but cannot establish historical contract identity or historical resolution semantics.

## A. Contract identity

A is adjudicated only from the canonical source-discovery v0.2 artifact and the frozen benchmark question.

`verified` requires all of the following:

1. a frozen Polymarket-origin or independently archived capture timestamped at or before `forecasted_at`;
2. the capture identifies the candidate's market/question;
3. the historical question equals the frozen benchmark question under the normalization already preregistered: Unicode normalization, line-ending normalization, trimming, and whitespace collapsing only;
4. the capture preserves enough historical rules/description to identify the contract semantics.

`contradicted` requires a qualifying pre-cutoff capture demonstrating materially different question identity or wording.

If no qualifying pre-cutoff capture exists in the frozen v0.2 discovery artifact, A is `unknown`. The adjudication stage does not reopen source-discovery or add newly discovered contract snapshots after seeing audit results.

Under the frozen v0.2 artifact, the only candidates eligible for A=`verified` are the three exact-match captured questions already frozen by source discovery. No candidate is added or removed based on later outcome evidence.

## B. Outcome unknowability

B asks whether the decisive real-world fact specified by the historical rules remained undecided at `forecasted_at`.

For candidates with A=`verified`, the decisive event/deadline must be derived from the frozen historical rules, never from a post-resolution reinterpretation.

Evidence hierarchy:

1. the primary resolution source explicitly named in the frozen historical rules;
2. an official first-party announcement, listing, status page, incident report, filing, or other authoritative record directly establishing the decisive fact;
3. only when the historical rules explicitly permit credible-reporting consensus, high-quality contemporaneous reporting may establish the decisive fact if the primary source is unavailable or insufficient.

The evidence record must preserve source URL, publisher/authority, publication timestamp when available, the event timestamp when separately stated, retrieval timestamp, and a SHA256 hash of the adjudicator's normalized evidence note or frozen source extract.

Status rules:

- `verified`: authoritative evidence places the decisive fact strictly after `forecasted_at`.
- `contradicted`: authoritative evidence places the decisive fact at or before `forecasted_at`.
- `unknown`: the decisive boundary cannot be established with adequate timestamped evidence.

`closedTime`, market resolution time, and price movement are not sufficient.

For candidates with A=`unknown`, B remains a required field but is `unknown` with reason `historical_contract_terms_unavailable` unless an authoritative source can establish the decisive boundary without relying on uncertain historical contract semantics. We do not use current/post-resolution market descriptions to manufacture historical rules.

## C. Authoritative final label

C verifies the canonical benchmark label independently of terminal market prices.

The canonical benchmark label may be read only after this protocol is committed, from the verified development-only custody derivative, never from the combined benchmark archive.

Evidence hierarchy:

1. a Polymarket/UMA resolution record tied to the market's resolution mechanism when available;
2. the primary authoritative source named by the verified historical rules;
3. when the historical rules explicitly allow credible-reporting consensus, sufficiently clear authoritative/credible contemporaneous reporting that determines the binary contract result.

The authoritative outcome must be represented only as `Yes` or `No`. The audit stores the canonical benchmark label separately and compares it mechanically.

Status rules:

- `verified`: independently supported authoritative outcome equals the canonical benchmark label;
- `contradicted`: independently supported authoritative outcome disagrees with the canonical benchmark label;
- `unknown`: adequate authoritative outcome evidence cannot be established.

For candidates with A=`unknown`, C remains represented but is `unknown` with reason `historical_contract_terms_unavailable` unless a resolution-mechanism record unambiguously ties the final label to the exact frozen market identity without requiring uncertain historical semantics.

## Frozen adjudication order

1. Verify artifact identities and the 64-row candidate membership.
2. Populate A mechanically from the frozen v0.2 source-discovery ledger and captured content.
3. Read canonical labels only from the verified development-only custody derivative and bind them by `question_id`; labels do not affect source selection.
4. Perform B/C public-source research only under the source hierarchy above.
5. Record every candidate, including all `unknown` and `invalid` cases.
6. Compute overall classification mechanically:
   - `verified_valid` iff A, B, and C are all `verified`;
   - `invalid` if any of A/B/C is `contradicted`;
   - `unknown` otherwise.
7. Freeze the full audit artifact before any forecaster is run on these 64 candidates.

No candidate may be replaced because its evidence is inconvenient or missing.

## Evidence freezing and reason codes

Each check stores a machine-readable status, reason code(s), evidence locators, source/publisher timestamps when available, and hashes of frozen supporting material or normalized adjudication notes.

Minimum reason codes include:

- `precutoff_contract_capture_exact_match`
- `precutoff_contract_capture_missing`
- `precutoff_contract_mismatch`
- `historical_contract_terms_unavailable`
- `decisive_fact_after_forecast`
- `decisive_fact_at_or_before_forecast`
- `decisive_fact_timestamp_unresolved`
- `authoritative_label_matches`
- `authoritative_label_disagrees`
- `authoritative_label_unresolved`

Additional narrow reason codes may describe transport/source availability, but they may not change the preregistered classification rules.

## Retrospective schedule limitation

Every output row carries `retrospective_close_anchored_schedule: true`. Passing this audit establishes historical internal validity only; it does not establish prospective deployability of the benchmark timing rule.

## Stage exit

The audit exits only when all 64 candidates have frozen A/B/C statuses and an overall classification. No forecaster is authorized during this stage.

Only `verified_valid` cases may later be considered for a separately preregistered fresh development-validation experiment. This protocol does not authorize opening the reserved holdout.