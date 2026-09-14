# Prospective Clustered Forecaster v0.1: Transport Recovery v2 Amendment

## Scope

This amendment applies only to provider transport behavior during timestamp-safe evidence acquisition for `prospective-clustered-residual-v2-v0.1`.

It does **not** change the frozen cohort, market questions, research cutoff, evidence sources, discovery query construction, article ordering, article-attempt budget, Common Crawl collection budget, evidence-item budget, visible-text limit, timestamp admission rules, model, residual mapping, scoring plan, or holdout boundary.

## Reason for amendment

The first sharded recovery run showed a systemic provider-transport failure pattern before any model forecasts or outcome access:

- Common Crawl index lookups repeatedly ended with server disconnects, timeouts, or HTTP 503 after the existing retry policy.
- GDELT requests also produced transient HTTP 429 responses under synchronized multi-runner access.

These are transport failures under the already frozen evidence-status clarification. They do not provide semantic evidence about any market outcome.

## Frozen transport-only changes

For the next provider-access attempt:

1. Preserve the same deterministic 77-row custody cohort and the same four-shard row assignment.
2. Preserve all previously terminal `verified_complete` and `verified_empty` checkpoints byte-for-byte. They may not be re-queried.
3. Retry only rows that are missing or whose latest checkpoint is `retrieval_failure`.
4. Stagger shard provider access deterministically by shard index so GDELT requests do not begin in a synchronized burst.
5. Use a GDELT minimum interval of 24 seconds per shard, 8 request attempts, and exponential retry backoff starting at 5 seconds, while continuing to honor provider `Retry-After` when present.
6. Use Common Crawl request timeout of 60 seconds, 8 request attempts, and exponential retry backoff starting at 2 seconds.
7. Pace Common Crawl HTTP requests within each shard by at least 1 second between requests. This pacing applies only to transport; it does not alter URL variants, crawl collections, ordering, capture selection, or evidence admission.
8. The bounded evidence search remains exactly: 90-day GDELT lookback, maximum 50 GDELT records, first 8 unique article URLs attempted, maximum 3 Common Crawl collections, maximum 5 admitted evidence items, and maximum 10,000 visible characters per item.
9. The dual timestamp gate remains unchanged: both GDELT `seendate` and Common Crawl capture timestamp must be at or before the frozen source cutoff.
10. A bounded search that completes with no admitted evidence and no unresolved provider failure remains `verified_empty`. Any unresolved provider/transport failure remains `retrieval_failure`.
11. No model forecast, outcome lookup, post-cutoff market price lookup, scoring, or reserved holdout access is authorized by this amendment.
12. Final evidence may be declared forecast-ready only after all 77 rows are terminal as `verified_complete` or `verified_empty`.

## Scientific boundary

This is an operational recovery amendment only. It is not a semantic evidence-policy change and must not be used to widen or substitute the frozen source universe. If the same providers remain systematically unavailable after this transport policy, any source substitution requires a separate amendment frozen before that source is queried.
