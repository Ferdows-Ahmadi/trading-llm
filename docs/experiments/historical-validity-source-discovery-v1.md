# Historical-validity source discovery v1

Status: frozen before querying current Polymarket locator metadata or Wayback capture availability for the 64 fresh candidates. The archive-provenance clarification below was committed before the first live source-discovery query.

Parent protocol: `docs/experiments/development-historical-validity-v1-preregistration.md`, preregistration commit `c3a66d28d7126155935ccdd255034e7560dce6f0`.

Candidate artifact:

- workflow run: `34738563200`
- artifact: `historical-validity-candidates-v0.1`
- artifact ID: `10312295819`
- artifact ZIP digest: `sha256:dc19595f7c59e8ddf9787c9a24530c9b32eedcccffedb1040754e4b0a48780af`
- candidate CSV SHA256: `6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21`
- rows/event groups: `64 / 64`

This stage is source discovery only. It does not adjudicate historical validity, run an LLM forecaster, inspect the reserved holdout, or use market outcomes/prices to select or drop candidates.

## Current Polymarket metadata as locator only

For every candidate, query current Gamma market metadata deterministically by the frozen numeric market ID (`question_id`). The first endpoint is:

```text
https://gamma-api.polymarket.com/markets/{market_id}
```

If that endpoint returns a definitive 404 only, use the deterministic fallback:

```text
https://gamma-api.polymarket.com/markets?id={market_id}
```

A fallback response is valid only if it resolves to exactly one object whose `id` equals the requested ID. Transport failures are recorded and retried; they never become `not found`.

Persist only locator/audit fields required to find historical or authoritative sources:

- market ID
- condition ID
- current question
- market slug
- description/resolution criteria text when supplied
- resolution-source locator when supplied
- created/start/end/closed/update timestamps when supplied
- event ID, event slug, event title, and event description when supplied

Do **not** persist current `outcomePrices`, live/final prices, volume, or other current price-derived outcome fields in the locator records. Current metadata cannot by itself satisfy the as-of contract-identity check.

## Frozen Wayback URL patterns

For every candidate with successful locator metadata, query the Wayback CDX index for the latest exact capture at or before the candidate `forecasted_at` for each applicable URL pattern below. No pattern is added or removed based on whether another pattern succeeds.

1. Gamma direct-market endpoint:

```text
https://gamma-api.polymarket.com/markets/{market_id}
```

2. Gamma query endpoint:

```text
https://gamma-api.polymarket.com/markets?id={market_id}
```

3. Polymarket event page, only when current locator metadata supplies a nonempty event slug:

```text
https://polymarket.com/event/{event_slug}
```

CDX lookup uses exact URL matching, status `200`, and accepts historical response MIME types containing `html` or `json`. The capture timestamp must be at or before `forecasted_at`. Scheme and leading `www.` variation may be accepted only when host, path, and query remain the same logical URL.

For each URL pattern record exactly one of:

- `capture`: latest qualifying pre-cutoff capture, with timestamp/original URL/MIME/status/digest/length/replay URL;
- `no_capture`: a successful CDX lookup returned no qualifying capture;
- `transport_failure`: lookup was not reliable after retries.

Every candidate remains in the output even if current locator retrieval or all Wayback lookups fail.

## Replay freeze

For each discovered `capture`, fetch the exact timestamped Wayback replay without following redirects to a different snapshot/resource. Persist raw bytes and SHA256. For JSON, also persist canonical parsed JSON SHA256 when parseable. For HTML, persist extracted visible text and SHA256. A replay transport/content failure is recorded rather than converted into `no_capture`.

Historical capture bodies are frozen before any case-level adjudication begins.

**Archive-provenance clarification:** a genuine pre-cutoff archived page/API response can naturally contain contemporaneous market-state fields, including the then-current probability. Such fields are historical source bytes, not the canonical benchmark outcome or the later-acquired benchmark `market_probability` column. They may remain inside the frozen raw replay solely so its provenance can be verified. Candidate selection and A/B/C historical-validity adjudication must not use those price fields. Current/post-resolution locator responses remain redacted as specified above. No archived replay content is model input during this audit stage.

## Contract-identity assistance

The discovery stage may compute non-adjudicative diagnostics:

- normalized frozen benchmark question hash;
- whether normalized benchmark question text is found exactly in a captured Gamma JSON object or archived event-page text;
- historical captured question hash when a Gamma JSON object exposes a question;
- historical description/resolution-criteria hash when exposed.

These diagnostics do not themselves assign `verified`, `contradicted`, or `unknown`; final A/B/C adjudication remains governed by the parent preregistration.

## Output and completeness

The artifact must contain all 64 candidates and all applicable URL-pattern lookup rows, including failures/no-capture rows. Summary counts may describe coverage but cannot remove candidates. Each output records:

- candidate artifact identity and candidate CSV hash;
- source-discovery code commit;
- parent preregistration commit;
- candidate question/event identity and forecast cutoff;
- redacted current locator status/metadata;
- every frozen URL pattern attempted;
- CDX lookup status;
- capture/replay identity and content hashes when available;
- explicit error class/message when unavailable.

No LLM inference, canonical benchmark outcome, prior model score, or reserved-holdout data is permitted in this artifact. Canonical benchmark market probabilities are not loaded. Any contemporaneous market state present inside a frozen pre-cutoff archive replay is provenance-only and forbidden from candidate selection or historical-validity adjudication.