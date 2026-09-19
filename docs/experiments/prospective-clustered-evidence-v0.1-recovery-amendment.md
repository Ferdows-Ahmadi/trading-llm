# Prospective Clustered Evidence v0.1 Recovery Amendment

## Status

This amendment is frozen before any recovery provider request. It changes transport/execution only. It does not change the scientific cohort, evidence cutoff, discovery query construction, source budgets, evidence admission rules, forecaster, residual mapping, or clustered analysis plan.

## Trigger

Canonical evidence run `34779255121` started from commit `6daabaae61dc76449b0ad9a38b5457e404dac3a4` and was cancelled by the GitHub Actions job timeout at 180 minutes while executing the evidence acquisition step. All preregistered pre-provider gates had passed, the immutable custody artifact had re-verified successfully, and the `if: always()` artifact upload preserved the partial checkpoint directory.

Partial recovery artifact:

- workflow run: `34779255121`
- artifact name: `prospective-clustered-evidence-v0.1`
- artifact ID: `10326569219`
- artifact ZIP digest: `sha256:c5a634563cbd2fddb5624750b17122edb7e1d2557b0f2a6780f8329f29540268`
- files uploaded: 55
- question checkpoints present: 33
- checkpoint terminal status at cancellation: 33 `retrieval_failure`
- no `verified_complete` or `verified_empty` checkpoint existed in this partial artifact
- 21 checkpointed rows had frozen GDELT response payloads; 12 checkpointed rows had no usable GDELT payload because discovery itself failed
- the remaining 44 custody rows had not reached a checkpoint before timeout

The observed provider-failure taxonomy was transport-only for recovery planning. Common Crawl connection failures dominated the checkpointed failures; GDELT transport failures also occurred. No outcome, resolution, post-cutoff market information, model output, or reserved holdout data was consulted in making this recovery decision.

## Frozen recovery rules

1. The frozen 77-row / 53-event v0.3 custody remains the complete denominator.
2. The original source cutoff `2026-09-13T19:14:39.226442Z` remains unchanged for every row.
3. The following scientific budgets remain unchanged: 90-day lookback, at most 50 GDELT records, at most 8 article URLs, at most 5 admitted evidence items, at most 3 Common Crawl collections, and at most 10,000 visible characters per item.
4. The original deterministic GDELT query builder, URL order, Common Crawl exact-page admission rules, dual pre-cutoff validation, and content-skip taxonomy remain unchanged.
5. Any checkpoint already in terminal state (`verified_complete` or `verified_empty`) must be reused byte-for-byte and may never be re-queried. The current partial artifact contains none, but this rule applies to every later recovery artifact.
6. A checkpoint in `retrieval_failure` may be retried. A row without a checkpoint may be attempted once under the frozen acquisition rules.
7. When a failed checkpoint has a frozen valid GDELT provider response from the original run, recovery may replay that exact provider response rather than issuing a new GDELT discovery request. This is a transport-recovery optimization only; it cannot change the discovered article ordering or candidate URLs for that attempt.
8. When no usable frozen GDELT response exists because the discovery request failed, GDELT may be retried under the unchanged query and budget.
9. Common Crawl lookup/fetch transport may be retried for `retrieval_failure` rows under the unchanged capture/admission rules.
10. Recovery work may be partitioned into deterministic shards solely to stay below hosted-run time limits. Sharding cannot alter row ordering, query construction, budgets, evidence admission, or final accounting.
11. Shard outputs must be merged deterministically by question ID. A terminal checkpoint takes precedence over a failed checkpoint for the same acquisition-context hash. Conflicting terminal checkpoints are a hard error.
12. A final evidence artifact is canonical only when all 77 rows are present, every row is terminal (`verified_complete` or `verified_empty`), all original custody/protocol hashes re-verify, and `forecast_ready=true`.
13. No model call is authorized until that final canonical evidence artifact and its fixture/packet/audit hashes are frozen.
14. Reserved holdout access, outcome lookup, later market-price lookup, and confirmatory claims remain forbidden.

## Rationale

The failed run demonstrated that a single serial hosted job is an inadequate transport envelope for the frozen acquisition workload. Parallel deterministic recovery and replay of already-frozen provider responses reduce repeated network work and timeout risk without changing which evidence is scientifically eligible. This amendment therefore repairs execution custody, not methodology.
