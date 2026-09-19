# Prospective clustered forecaster v0.1 evidence-status clarification

Status: frozen before the first GDELT or Common Crawl request for the v0.3 cohort and before any model forecast.

Parent forecaster preregistration commit: `d6f242b78a983bcd059384a68a5c05954dfc99f2`.

Schema-binding clarification commit: `87436e7164489a1699fec81d8cc845ceeca55012`.

This clarification defines the operational boundary between a provider/retrieval failure and a deterministically checked URL that yields no admissible evidence. It changes no source, cutoff, query, ordering, item cap, URL-attempt cap, collection cap, character cap, model, prompt, or probability rule.

## Retrieval failure

A row is `retrieval_failure` if the bounded acquisition cannot be completed because a required provider operation remains unavailable after the existing frozen client retry policy, including:

- GDELT request transport failure, terminal rate-limit failure, or terminal provider HTTP/server failure;
- Common Crawl collection-index or CDX lookup transport/provider failure after retries;
- Common Crawl WARC range request transport failure or terminal provider HTTP failure after retries.

A row with any such unresolved required provider failure is not forecast-ready even if other evidence items were successfully obtained.

## Deterministic non-evidence skips

The following are completed checks, not retrieval failures, and the attempted URL may be skipped without making the row incomplete:

- GDELT returns no matching article records;
- Common Crawl returns no eligible exact-page pre-cutoff capture;
- a returned record/capture is malformed and therefore cannot satisfy the frozen admission contract;
- duplicate capture digest;
- capture does not satisfy the frozen HTTP-200/HTML/pre-cutoff/path requirements;
- a successfully retrieved WARC record contains no usable response body, cannot be parsed into admissible article content, or produces fewer than the existing minimum visible-text requirement;
- extracted text is empty or otherwise fails the existing deterministic content requirements;
- deterministic query construction finds no usable discovery terms in the frozen question text.

These conditions provide no admitted evidence item. They do not authorize another source, looser path match, current/live webpage content, or manual repair.

If the entire bounded search completes with zero admitted items and no unresolved provider failure, the row is `verified_empty` and receives the preregistered exact-market hard no-op.

If one or more items are admitted, the bounded search completes, and no unresolved provider failure occurred, the row is `verified_complete`.

All attempt outcomes and reason codes must be persisted in the evidence audit artifact so `verified_empty` can be distinguished from an acquisition that was never actually completed.
