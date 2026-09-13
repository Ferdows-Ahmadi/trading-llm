# Historical Validity Source Discovery v2: Shard 1 Recovery Execution Plan

Status: frozen before any recovery acquisition query.

This document changes execution only. It does not change the frozen v2 scientific acquisition protocol, candidate cohort, URL derivation rules, provider set/order, historical cutoff logic, Common Crawl collection bound, source eligibility rules, validity definitions, forecasting logic, scoring logic, or reserved-holdout custody.

## Trigger for recovery

Historical Validity Source Discovery v0.2 run `34758856382` used the execution-only 4 x 16 deterministic contiguous sharding scheme at acquisition-code commit `70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2`.

Shards 0, 2, and 3 completed successfully. Shard 1 entered source acquisition and was cancelled at the configured 90-minute job timeout before finalizing its output. The final four-shard merge was therefore correctly skipped.

The timeout is treated as an execution/runtime failure, not as a scientific result.

## Reused completed artifacts

The following successful artifacts from run `34758856382` are retained unchanged:

- shard 0: artifact ID `10318785658`, archive digest `sha256:9f74f8a27e2ff357d09b0dabec61b9db18eb40ffb604688650e8ac082f297ec5`
- shard 2: artifact ID `10317979396`, archive digest `sha256:454aebe3a863664e2c1098af3ea15b793497fef01bbee4dfcbeadc535aaaf6ee`
- shard 3: artifact ID `10318148617`, archive digest `sha256:4fb96eb661d2bb0e1d3182d4f9124a26f022b31c6f61d49e09b50f9133033fd0`

All three successful artifacts record the same Common Crawl collection-manifest digest:

`9134eeb9976c3cbbbaff9830c007419dd300d5f7396b2268f4618e51441d274c`

The recovery workflow will obtain `commoncrawl-collections.json` from the immutable shard-0 artifact above, verify the artifact identity and the manifest digest, and use that exact manifest as a frozen input for every shard-1 recovery acquisition. It will not re-fetch the live Common Crawl collection manifest.

## Frozen acquisition code versus recovery orchestration

The scientific/acquisition implementation remains pinned to:

`70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2`

Recovery orchestration and reconstruction code may live at a later commit. The workflow must record that later commit separately as the orchestration commit.

For every recovery acquisition job:

1. the workflow checks out the orchestration commit for the recovery runner;
2. it separately checks out commit `70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2` for the Prediction Lab package;
3. the Prediction Lab package used by the acquisition process is installed from that frozen checkout;
4. the recovery runner calls the unchanged `discover_v2_sources()` and unchanged v2 provider classes from that frozen package;
5. `code_commit` remains the frozen acquisition-code commit, while `orchestration_commit` records the workflow/recovery commit.

The existing `historical_validity_sources_v2.py` and `historical_validity_sources_v2_sharded.py` at the frozen acquisition commit are not modified for recovery.

## Exact shard-1 membership

Original shard 1 is the contiguous parent-candidate slice at zero-based rows 16 through 31, inclusive, of the frozen 64-row candidate CSV.

Its question IDs, in frozen parent order, are:

1. `716634`
2. `967152`
3. `973201`
4. `1038582`
5. `1145524`
6. `1175296`
7. `690700`
8. `701600`
9. `704075`
10. `701719`
11. `701576`
12. `1143797`
13. `701499`
14. `1271641`
15. `690698`
16. `701766`

No candidate may be replaced, reordered, selected by runtime cost, outcome, market probability, prior evidence, prior model output, or archive result.

## Recovery partition

Shard 1 is partitioned into 16 deterministic one-row recovery subshards. Recovery subshard index `i` contains exactly parent-candidate row `16 + i` and no other candidate.

The recovery matrix uses:

- 16 entries, indices 0 through 15;
- one candidate per entry;
- `timeout-minutes: 30` per acquisition job;
- `max-parallel: 6` to limit archive-provider pressure while avoiding a long serial wall clock.

A timeout or provider failure in one one-row job does not change the membership or rules of any other job. Failed recovery subshards must be reported and retried under the same frozen inputs and rules; they may not be silently dropped or replaced.

## Common Crawl pinning

Each recovery subshard must use the exact frozen Common Crawl collection list from the original successful shard-0 artifact.

The recovery runner may preload that list into the unchanged frozen `CommonCrawlV2Provider` client cache so that `_eligible_collections()` operates over the pinned list rather than issuing a new `collinfo.json` request. The maximum eligible collection count remains exactly `6` as frozen in v2.

This is an execution/provenance constraint to preserve the original run's Common Crawl collection universe. It does not add, remove, reorder, or otherwise alter candidate URL patterns or capture eligibility logic.

## Wayback wall-clock acquisition state

Wayback/CDX is queried later in wall-clock time for the shard-1 recovery subshards. Historical capture eligibility remains governed by the same candidate forecast cutoff and frozen v2 rules.

The final artifact must record acquisition timestamps for recovery subshards. It must not claim that all 64 candidates were queried against one simultaneous snapshot of the Wayback index.

## Shard-1 reconstruction

After all 16 one-row recovery artifacts complete, a reconstruction step must verify and combine them into one directory shaped as original shard 1 for the existing trusted four-shard merge.

The reconstructed shard-1 artifact must preserve the original required fields:

- `shard_index: 1`
- `shard_count: 4`
- `shard_size: 16`
- the exact 16 question IDs above in original order
- `code_commit: 70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2`
- the frozen parent candidate digest and v1 artifact identity
- the pinned Common Crawl manifest and digest

It must also explicitly record recovery provenance, including:

- `execution_mode: reconstructed-from-single-row-subshards`
- orchestration/reconstruction commit
- every recovery subshard artifact name, immutable artifact ID, archive digest, question ID, and acquisition timestamp
- recovery partition geometry

Raw/text content remains content-addressed and duplicate names must be byte-identical.

The reconstructed ledger must contain every lookup row from all 16 recovery subshards, ordered by the original parent candidate order, with no duplicated lookup key and no omitted candidate.

## Final canonical merge

The existing `merge_shards()` implementation from acquisition-code commit `70e1e0dedfd261dc00dc53e9be05b784d5a2f1a2` must be used unchanged for the final merge.

Its inputs are:

- original successful shard 0 artifact, unchanged;
- reconstructed shard 1 artifact;
- original successful shard 2 artifact, unchanged;
- original successful shard 3 artifact, unchanged.

The merge must still enforce exact 64-candidate membership, original shard geometry, provider/status vocabulary, duplicate-key rejection, Common Crawl manifest identity, acquisition-code commit equality, and byte identity for duplicate content-addressed files.

The final canonical v2 artifact is uploaded only if the unchanged merge succeeds.

## Interpretation boundary

This recovery performs historical source discovery only. It does not perform A/B/C historical-validity adjudication, forecasting, residual-v2 inference, scoring, model selection, or reserved-holdout analysis.
