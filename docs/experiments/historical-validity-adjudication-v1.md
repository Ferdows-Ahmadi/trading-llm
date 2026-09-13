# Historical-validity adjudication v1

Status: frozen after completion of historical source discovery v0.2 and inspection of the canonical source-discovery artifact, but **before any new live acquisition of criterion-B or criterion-C evidence and before any fresh forecaster evaluation**.

This protocol implements the adjudication stage already defined by `development-historical-validity-v1-preregistration.md`. It does not change candidate membership, the A/B/C definitions, or the overall classification rule.

## Purpose

The immediate scientific task is to determine which of the 64 frozen fresh-development candidates are defensible historical forecasting cases.

This stage performs no forecasting, no model scoring, no residual-v2 inference, and no holdout access.

Every one of the 64 frozen candidates must remain represented in the final audit artifact, including cases that remain `unknown`.

## Frozen inputs

Candidate artifact:

- artifact: `historical-validity-candidates-v0.1`
- artifact ID: `10312295819`
- candidate CSV SHA256: `6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21`
- rows: `64`
- event groups: `64`

Canonical source-discovery artifact:

- artifact: `historical-validity-source-discovery-v0.2-canonical`
- artifact ID: `10320984640`
- digest: `sha256:aee2e398b421bd8b2a94fbfd3f5edf2c6fb28c2b71f490e8a98c60ee3b8c7648`
- workflow run: `34767754110`
- acquisition-code commit: `70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2`
- orchestration commit: `f77268443670b205a62b7e751408f53b691049b9`

Source-discovery accounting is frozen as:

- candidate rows: `64`
- source lookup rows: `384`
- captures: `3`
- exact-question-match diagnostics: `3`
- no-capture: `356`
- transport-failure: `25`
- content-failure: `0`
- no-url: `0`

A missing archive capture is not evidence of historical invalidity.

## Captures observed before this protocol

The canonical source-discovery artifact contains exactly three pre-cutoff captures with exact normalized benchmark-question matches:

1. question `1068359`, event `polymarket-event:133720`
   - benchmark question: `Hyperliquid listed on Coinbase before 2027?`
   - forecasted at: `2026-01-30T09:51:18Z`
   - Wayback capture: `2026-01-07T17:03:48Z`
   - archived rules specify Yes if Hyperliquid (`$HYPE`) is listed for spot purchase on Coinbase by December 31, 2026, 11:59 PM ET; Coinbase is the primary resolution source, with credible reporting as fallback.
   - raw SHA256: `1112c6323a7fcf983d848fa78352b30ff71593a157b95cc07805c26e317774f4`
   - extracted-text SHA256: `218d34ca8f0d66efbf0b18ecf75ecc0a64bb11ef3a21d03dace479d86f87500e`

2. question `1251725`, event `polymarket-event:184020`
   - benchmark question: `Will Binance launch stock tokens in 2026?`
   - forecasted at: `2026-02-17T23:16:59Z`
   - Wayback capture: `2026-01-23T21:41:17Z`
   - archived rules specify Yes if Binance offers tokenized versions of U.S.-listed equities for users to buy or sell on its platform by December 31, 2026, 11:59 PM ET; Binance is the primary resolution source, with credible reporting as fallback.
   - raw SHA256: `98737607c7a6549afb8313e323dfb4a5c21e9082caef4a21705ec741832c86e1`
   - extracted-text SHA256: `f9195d3ce8bd7e47b41b53c66924125305035127f64bdc3f5b950ea37fec7b34`

3. question `1832174`, event `polymarket-event:336641`
   - benchmark question: `Another crypto hack over $100m by December 31?`
   - forecasted at: `2026-04-12T15:47:37Z`
   - Wayback capture: `2026-04-04T08:16:39Z`
   - archived rules specify Yes if any crypto project or exchange suffers an exploit or hack worth at least USD 100 million equivalent between market creation and December 31, 2026, 11:59 PM ET; the Rekt News leaderboard is the primary resolution source, with credible reporting as fallback.
   - raw SHA256: `07cc82e15de36248f1f34a676ccd75184c80c9032f34d9cbd15527a2423eafcc`
   - extracted-text SHA256: `361fb0cbb3a06b997ee84ba27d24e42275d3a982955936638099878cb99ecee8`

These identities were observed during source discovery and may be used for adjudication. They were not selected because of outcomes or model performance.

## Criterion A: contract identity as of forecast time

Criterion A is evaluated only from timestamped evidence available at or before the candidate's `forecasted_at`.

Allowed evidence:

- canonical frozen source-discovery captures;
- a later adjudication source only if it is itself an independently timestamped pre-cutoff archive satisfying the original historical-validity definition.

Current or post-resolution metadata may be used as a locator but cannot independently verify A.

Status rules:

- `verified`: a pre-cutoff source establishes the exact historical contract and normalized historical question equals the frozen benchmark question.
- `contradicted`: a pre-cutoff source establishes materially different question wording or incompatible contract identity.
- `unknown`: adequate pre-cutoff evidence is unavailable.

For machine verification, normalization remains limited to Unicode normalization, line-ending normalization, trimming, and collapsing whitespace. Semantic paraphrase is not equality.

Where the frozen capture contains rules/description text, the audit must preserve a hash of that text or of the full extracted archive text used to establish the rules.

## Criterion B: outcome unknowability at forecast time

Criterion B asks whether the decisive real-world fact was still unresolved strictly after `forecasted_at`.

The adjudicator must first derive a structured `decisive_condition` from the historical contract rules without using the benchmark outcome or later model result.

Eligible B evidence must be timestamped and authoritative enough to establish when the decisive condition became true, false, or impossible.

Preferred source hierarchy:

1. the primary resolution source named by the historical contract;
2. an official first-party source for the underlying event;
3. multiple reputable independent reports when the contract explicitly allows consensus reporting or the primary source is unavailable.

A market close timestamp alone is never sufficient.

Status rules:

- `verified`: evidence establishes that the decisive event/fact occurred strictly after `forecasted_at`, or that the contract remained genuinely undecided until a deadline strictly after `forecasted_at`.
- `contradicted`: evidence establishes that the decisive event/fact had already occurred or become objectively settled at or before `forecasted_at`.
- `unknown`: timing cannot be established adequately.

The artifact must record the decisive event/deadline timestamp when established, source publication timestamp when available, source locator, and reason code.

## Criterion C: authoritative final label

Criterion C verifies the benchmark Yes/No label independently of terminal market price.

Eligible C evidence follows the historical contract's stated resolution mechanism where possible.

Preferred source hierarchy:

1. the named primary resolution source;
2. an official Polymarket resolution record tied to the resolution mechanism;
3. an official first-party source proving the underlying condition;
4. credible reporting consensus only where the historical rules permit it or where the authoritative fact is independently unambiguous.

Terminal near-1/0 `outcomePrices`, last-trade prices, or market-implied probabilities cannot satisfy C.

Status rules:

- `verified`: authoritative evidence supports a binary Yes/No final label and it agrees with the canonical benchmark label.
- `contradicted`: authoritative evidence supports a binary label that disagrees with the canonical benchmark label.
- `unknown`: adequate independent final-label evidence cannot be established.

The authoritative outcome must be stored separately from the canonical benchmark label so disagreement cannot be hidden.

## Evidence acquisition and freezing

New B/C evidence acquisition begins only after this protocol is committed.

For every acquired source used in a decision, persist at minimum:

- criterion (`B` or `C`, or `A` only for a newly found eligible pre-cutoff archive);
- question ID;
- source URL/locator;
- source type and source authority class;
- retrieval timestamp;
- publication/event timestamp where available;
- raw-response SHA256 when raw bytes can be frozen lawfully and technically;
- extracted-text SHA256 when extraction is performed;
- short structured fact used for adjudication;
- decision status and reason code.

Search-engine snippets alone are not admissible decision evidence. They may be used only to locate the underlying source.

If a source is mutable and raw freezing is not technically available, the audit records the retrieval timestamp and exact locator and treats the limitation explicitly rather than fabricating immutability.

## No forecasting-model participation

The forecasting LLM/model may not adjudicate A/B/C.

No adaptive forecaster output, correctness, residual direction, confidence, evidence-bearing status, Brier contribution, or market-vs-model comparison may be shown to the adjudicator or used to choose sources.

General-purpose tooling may assist deterministic parsing and evidence extraction, but the adjudication ledger must expose the source facts and reason codes directly.

## Overall classification

For every candidate:

- `verified_valid` only if A, B, and C are all `verified`;
- `invalid` if any of A, B, or C is `contradicted`;
- `unknown` otherwise.

Unknown candidates remain in the artifact and are excluded from later scoring rather than silently removed.

## Frozen audit schema

Each of the 64 candidate rows must contain at least:

- `question_id`
- `question_text`
- `event_id`
- `category`
- `forecasted_at`
- `source_cutoff_at`
- `normalized_question_sha256`
- `criterion_a_status`
- `criterion_a_reason_code`
- `criterion_a_evidence_refs`
- `historical_question_sha256`
- `historical_rules_or_text_sha256`
- `criterion_b_status`
- `criterion_b_reason_code`
- `criterion_b_evidence_refs`
- `decisive_condition`
- `decisive_event_at`
- `criterion_c_status`
- `criterion_c_reason_code`
- `criterion_c_evidence_refs`
- `authoritative_outcome`
- `canonical_outcome`
- `overall_status`
- `retrospective_close_anchored_schedule`
- `candidate_sha256`
- `source_discovery_artifact_id`
- `source_discovery_artifact_digest`
- `adjudication_code_commit`

Evidence references may point into a separate immutable evidence ledger rather than duplicating full source metadata in every row.

## Failure accounting

The audit must fail closed on malformed candidate identity, duplicate question IDs, altered candidate SHA, unknown status vocabulary, broken evidence references, or disagreement between overall status and criterion statuses.

Source retrieval failures do not delete candidates. They produce explicit evidence acquisition records and normally leave the affected criterion `unknown` unless other admissible evidence resolves it.

## Stage exit

The adjudication stage ends only when:

1. all 64 candidates are represented;
2. every A/B/C field is explicitly `verified`, `contradicted`, or `unknown`;
3. every non-unknown judgment has traceable admissible evidence;
4. the complete audit and evidence ledger are frozen with hashes and code identity;
5. summary counts are generated without model forecasting results.

Only then may the project inspect how many `verified_valid` cases exist and design the separate fresh development-validation preregistration.

This protocol does not authorize residual-v2, fresh Brier scoring, or access to the 73-case reserved holdout.