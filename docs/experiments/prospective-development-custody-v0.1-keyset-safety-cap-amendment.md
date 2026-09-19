# Prospective development custody v0.1 keyset safety-cap amendment

Status: frozen before any retry after the first correctly wired keyset acquisition reached the preregistered 100-page safety limit.

Parent protocol: `docs/experiments/prospective-development-custody-v0.1-preregistration.md`, commit `1562a16f835f1b75f878341146fa7a867f2439e5`.

Parent pagination amendment: `docs/experiments/prospective-development-custody-v0.1-pagination-amendment.md`, commit `e1f2570c9f0f342d41426c411fc8c8bbeafd8bc1`.

## Trigger for this amendment

GitHub Actions run `34775981813`, code commit `ad4008ebc6916321c2e86a6802b86c02c65c485d`, passed the frozen pre-live contract checks and seven custody/keyset tests, then used the authorized `GET /markets/keyset` transport. The collector received 100 successive pages with non-empty, non-repeated cursors and deliberately failed at the frozen 100-page safety limit.

That run did **not** complete custody and did not upload a cohort artifact. No selected question text, selected market probability, cohort membership, model output, outcome, or model-versus-market result was inspected. The only new information used for this amendment is the transport-level fact that the complete filtered universe requires more than 100 keyset pages under the frozen request.

## External API constraint checked before amendment

Polymarket's official keyset documentation states that `limit` has a maximum value of 100, that `next_cursor` is returned for full pages, and that the exact opaque cursor is supplied as `after_cursor` for the next request. Therefore the existing `limit=100` is already maximal and cannot be increased to solve the safety-cap failure.

Official reference:

`https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination`

## Frozen amendment

Only the keyset transport safety ceiling changes.

- Keep `limit=100`.
- Keep the exact frozen request filters, ordering, cursor handling, raw-response freezing, duplicate-ID rejection, repeated-cursor rejection, malformed-cursor rejection, and all scientific selection rules unchanged.
- Replace the keyset-specific 100-page safety ceiling with a keyset-specific ceiling of **1,000 pages** (at most 100,000 returned market rows before any structural filtering).
- The collector must still terminate normally only when `next_cursor` is absent or empty.
- If a non-empty cursor remains after page 1,000, the run must fail rather than truncate the universe.
- The legacy offset collector's own constants and behavior are not changed; this amendment applies only to the authorized keyset recovery module.

The retry establishes a new `snapshot_reference_at` immediately before its first keyset request. Failed incomplete runs are not reused as timing anchors and cannot become alternative cohorts.

## What does not change

Everything scientific remains as frozen in the parent protocol and first pagination amendment, including:

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

The first run that completes the full keyset universe under this amendment and uploads an immutable custody artifact is the only cohort for this protocol. A completed artifact may not be replaced by rerunning acquisition to obtain a more favorable cohort.
