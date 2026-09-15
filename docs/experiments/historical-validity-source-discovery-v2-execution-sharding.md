# Historical Validity Source Discovery v2: execution sharding clarification

Status: frozen before any sharded acquisition run.

This document changes execution only. It does not change the scientific source-discovery protocol, candidate membership, URL derivation, archive providers, cutoff timestamps, Common Crawl collection bound, matching diagnostics, or any validity/adjudication rule.

## Motivation

The first full v2 acquisition attempt on GitHub Actions reached the workflow's 90-minute execution limit before completing all 64 frozen candidates. The timeout occurred during archive acquisition after the frozen contract, tests, lint, and exact input downloads had passed. A partial artifact was uploaded, demonstrating that the acquisition path can freeze historical content, but it did not contain a complete lookup ledger or summary.

## Frozen execution rule

The existing 64-row candidate file remains the sole parent candidate set and retains SHA256:

`6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21`

Execution is partitioned into exactly four deterministic contiguous shards of 16 rows each, using the existing row order in the frozen candidate CSV:

- shard 0: rows 0-15
- shard 1: rows 16-31
- shard 2: rows 32-47
- shard 3: rows 48-63

Each shard must use the same v2 URL derivation, Wayback provider, Common Crawl provider, forecast cutoff, retry behavior, content-freezing logic, and six-collection Common Crawl bound already frozen for v2. Sharding must not inspect outcomes, market probabilities, prior model forecasts, prior v0.5 results, or reserved holdout contents.

Each shard records its parent candidate SHA, exact shard index/count, subset question IDs, subset CSV SHA, code commit, and Common Crawl collection-manifest SHA.

## Merge rule

A final deterministic merge is permitted only when all four shards succeed. The merge must verify:

1. shard indices are exactly `{0,1,2,3}` with no duplicates;
2. every shard points to the same frozen parent candidate SHA and code commit;
3. the union of shard question IDs equals the exact 64 IDs in the frozen parent candidate file, with no duplicates or omissions;
4. all shard Common Crawl collection-manifest SHA values are identical;
5. duplicate frozen raw/text files, if any, are byte-identical;
6. every lookup status belongs to the existing v2 status vocabulary;
7. providers remain limited to the already registered v2 providers;
8. the final ledger preserves parent-candidate row order and the existing within-candidate lookup order.

The merged artifact recomputes the existing v2 aggregate counts from the merged ledger. No row may be dropped because of transport failure, content failure, no capture, or no URL.

## Interpretation

This clarification is scientifically inert. It exists only to prevent infrastructure timeout from truncating an otherwise unchanged acquisition protocol. The earlier timed-out artifact remains a partial engineering artifact and is not a canonical v2 scientific result.
