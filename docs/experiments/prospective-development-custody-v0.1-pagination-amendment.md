# Prospective development custody v0.1 pagination amendment

Status: frozen before any retry after the first live acquisition attempt failed.

Parent protocol: `docs/experiments/prospective-development-custody-v0.1-preregistration.md`, commit `1562a16f835f1b75f878341146fa7a867f2439e5`.

## Why this amendment is necessary

The first workflow that passed all pre-live tests and reached the live acquisition step was run `34773018206`, code commit `a5b4b508aeb6604d4623be3d81716c8687555ffe`.

That run did **not** complete custody and did not upload a cohort artifact. It failed while paging the Gamma market universe because the legacy offset endpoint returned HTTP 422:

`offset too large, use /markets/keyset for deeper pagination`

No selected question text, selected market probability, cohort membership, model output, outcome, or model-versus-market result from that failed run was printed or inspected. The failure log exposed only the transport/API validation error above. The runner's temporary partial responses were destroyed with the failed job and are not treated as a cohort artifact.

Polymarket's official API documentation defines `GET https://gamma-api.polymarket.com/markets/keyset` as the supported cursor-based market-list endpoint for deep pagination. It accepts the same relevant filters and ordering parameters, returns a `markets` array plus an opaque `next_cursor`, and requires that cursor to be passed back as `after_cursor`. The keyset endpoint explicitly rejects `offset`.

Official reference used for this engineering correction before retry:

`https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination`

## Frozen amendment

Only the pagination transport is changed. All scientific selection, timing, custody, price, independence, adequacy, and no-replacement rules from the parent protocol remain unchanged.

The authorized market-universe request is now:

`GET https://gamma-api.polymarket.com/markets/keyset`

with the same frozen query values:

- `closed=false`;
- `end_date_min=<snapshot_reference_at + 7 days>`;
- `end_date_max=<snapshot_reference_at + 45 days>`;
- `order=id`;
- `ascending=true`;
- `limit=100`.

Pagination is:

1. first page omits `after_cursor`;
2. each successful response must be a JSON object containing a `markets` array;
3. if a non-empty `next_cursor` is returned, the exact opaque value is passed as `after_cursor` on the next page;
4. acquisition ends when `next_cursor` is absent or empty;
5. the collector must reject a repeated cursor, duplicate market ID across pages, malformed cursor type, or more than 100 pages rather than silently truncating or looping;
6. every complete raw keyset response, including its `next_cursor`, is frozen before normalized selection output is produced.

The retry establishes a new `snapshot_reference_at` immediately before its first keyset request. The failed run is not reused as a timing anchor because it produced no immutable complete universe artifact. This choice is frozen here before the retry and before any complete cohort membership is known.

## What does not change

The following remain exactly as preregistered:

- one-time development-validation cohort intent;
- target 100 event-independent markets;
- adequacy floor 60 eventually resolved and adjudicable cases;
- selection seed `prospective-development-custody-v0.1-selection-seed-2026-09-13`;
- 7-to-45-day scheduled-end window;
- all structural eligibility thresholds and requirements;
- deterministic parent-event representative rule;
- no fallback to another market from an event;
- CLOB Yes-token bid/ask/midpoint acquisition and spread rule;
- deterministic final event ranking;
- no discretionary replacement;
- no model inference or scoring during custody;
- no selected question/probability inspection before the later evidence/forecaster protocol is frozen;
- reserved holdout remains inaccessible.

## Retry rule

A retry under this amendment is an engineering recovery of the incomplete acquisition, not permission to adapt selection based on observed market content. If the keyset acquisition completes and the immutable custody artifact is uploaded, that artifact is the only cohort for this protocol. Later retries may not create a preferred alternate cohort.
