# Historical-validity source discovery v2

Status: frozen before querying any v2 historical-source endpoint or capture index.

Parent historical-validity protocol: `docs/experiments/development-historical-validity-v1-preregistration.md`.

Fresh candidate cohort:

- artifact: `historical-validity-candidates-v0.1`
- workflow run: `34738563200`
- artifact ID: `10312295819`
- artifact ZIP digest: `sha256:dc19595f7c59e8ddf9787c9a24530c9b32eedcccffedb1040754e4b0a48780af`
- candidate CSV SHA256: `6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21`
- rows/event groups: `64 / 64`

Frozen v1 locator artifact:

- workflow run: `34739814494`
- artifact: `historical-validity-source-discovery-v0.1`
- artifact ID: `10311998928`
- artifact ZIP digest: `sha256:fa1b454d5a44699f7f314db5871268d416856db369bc6e58c2c54d8b79047622`
- code commit: `ef5d0c7159f662af1099e089349698310c931183`
- v1 result: `64/64` current Gamma locators succeeded, `128` frozen URL lookups were attempted, `0` usable pre-cutoff captures were found, and `7` lookup transport failures were recorded.

This v2 stage expands source discovery only. It does not adjudicate historical validity, inspect benchmark outcomes or market probabilities, run an LLM forecaster, alter the 64-candidate cohort, or access the reserved holdout.

## Why v2 exists

The v1 route searched the two ID-based Gamma API URLs for each candidate and found no usable pre-cutoff captures. API endpoints are not sufficient archival targets for the historical-contract audit. v2 therefore adds deterministic human-facing Polymarket URL patterns and slug-addressed Gamma patterns while preserving every v1 result unchanged.

## Frozen locator inputs

V2 consumes the redacted current locator ledger frozen by v1. Only fields already allowed by v1 may be used to derive additional URLs. In particular, v2 may use:

- numeric market ID;
- condition ID;
- market question and market slug;
- description/resolution-source locator text;
- non-price timestamps;
- nested event slug/title/description when present.

V2 must not read or reconstruct `outcomePrices`, final/live prices, volume, best bid/ask, last trade price, benchmark labels, prior model predictions, prior model scores, or any reserved-holdout field.

Every candidate remains in the output regardless of lookup success.

## Frozen v2 URL derivation

For each candidate with a nonempty market slug in the frozen v1 locator, derive all of the following URL patterns before any archive result is inspected:

1. Human-facing market page:

```text
https://polymarket.com/market/{market_slug}
```

2. Human-facing event page using the market slug:

```text
https://polymarket.com/event/{market_slug}
```

3. Gamma market-by-slug endpoint:

```text
https://gamma-api.polymarket.com/markets/slug/{market_slug}
```

For every nonempty nested event slug already present in the frozen v1 locator, also derive:

4. Human-facing event page using the event slug:

```text
https://polymarket.com/event/{event_slug}
```

5. Gamma event-by-slug endpoint:

```text
https://gamma-api.polymarket.com/events/slug/{event_slug}
```

Duplicate URLs are de-duplicated deterministically per candidate after all applicable patterns are generated. Slugs must match a conservative ASCII URL-safe allowlist; unsafe or missing slugs are recorded explicitly and never guessed from question text.

No additional URL pattern may be added for an individual candidate based on whether another pattern succeeds or fails.

## Archive providers

Each frozen v2 URL is queried against both providers below, independently.

### A. Wayback CDX

Query the latest qualifying capture at or before candidate `forecasted_at` using exact URL matching. Accept HTTP status `200` and historical MIME types containing `html` or `json`. Scheme and leading `www.` variation may be accepted only when host, path, and query represent the same logical URL.

Record exactly one of:

- `capture`;
- `no_capture`;
- `transport_failure`.

### B. Common Crawl index

Query the same exact URL against the frozen Common Crawl collection list returned by the provider at run start. Collections are inspected newest-to-oldest, but only captures whose WARC record timestamp is at or before candidate `forecasted_at` qualify. Exact logical URL matching is required after normalization; no prefix/domain/wildcard match is accepted for the canonical v2 result.

Record exactly one of:

- `capture`;
- `no_capture`;
- `transport_failure`.

Provider failure never becomes `no_capture`. A candidate is not dropped because one provider fails.

## Replay/content freeze

For each discovered capture, fetch the exact archived body represented by that capture and persist:

- provider;
- requested URL and captured/original URL;
- archive timestamp;
- provider record identity/digest when supplied;
- raw bytes SHA256;
- byte length;
- canonical parsed JSON SHA256 when parseable JSON;
- extracted visible-text SHA256 and character count for HTML;
- deterministic content/replay failure status when the body cannot be frozen.

Historical capture bodies are frozen before case-level adjudication.

## Non-adjudicative diagnostics

V2 may compute only diagnostics that assist later contract-identity review, including:

- normalized benchmark-question SHA256;
- normalized archived question SHA256 when exposed;
- exact normalized benchmark-question match in archived JSON or visible text;
- archived description/rules SHA256 when exposed;
- archived resolution-source locator text when exposed.

These diagnostics do not themselves classify a case as historically valid or invalid.

## Completeness and preservation

The v2 artifact must include all 64 candidate IDs and a ledger row for every deterministic candidate/provider/URL combination, including `no_capture`, `transport_failure`, and replay/content failures.

The artifact must record:

- exact candidate artifact identity and CSV SHA256;
- exact v1 locator artifact identity/digest;
- v2 protocol commit;
- v2 implementation commit;
- provider collection/index identity where applicable;
- all generated URL patterns;
- all lookup statuses;
- all frozen capture/content hashes;
- explicit error class/message for unreliable lookups.

V1 remains immutable and is not reinterpreted as success or failure based on v2. V2 is an archival-source expansion only. It may improve coverage, but it cannot alter candidate membership, historical-validity criteria, the residual forecasting method, statistical decision rules, or holdout custody.
