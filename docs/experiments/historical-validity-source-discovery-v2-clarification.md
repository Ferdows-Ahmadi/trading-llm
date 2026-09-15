# Historical-validity source discovery v2 clarification

Status: frozen before any v2 archive lookup is executed.

Parent v2 protocol commit: `97ac0e7ee15c0b315a6369a4a955f5f3b078ed57`.

This clarification fixes implementation bounds that the parent protocol left underspecified. It does not change candidate membership, source URL derivation, historical-validity criteria, or any forecasting method.

## Common Crawl bounded collection rule

Inspect at most the six newest Common Crawl collections whose advertised `from` timestamp is at or before the candidate `forecasted_at`, newest first. This is a fixed acquisition budget applied uniformly to every candidate/URL. It is chosen before any v2 lookup result is observed.

Within each inspected collection, query exact logical URL only. A qualifying capture must:

- have capture timestamp at or before `forecasted_at`;
- resolve to the same normalized host/path/query as requested, allowing only scheme and leading `www.` variation;
- have HTTP status `200`;
- have a MIME type containing `html` or `json`.

Stop after the first inspected collection that yields one or more qualifying captures and freeze the latest qualifying capture in that collection. If none of the six collections yields a capture and any inspected collection had an unreliable transport/provider response, record `transport_failure`; otherwise record `no_capture`.

The exact Common Crawl `collinfo.json` payload used by the run must be hashed and recorded in the artifact.

## Replay/content rule

For Common Crawl, the archived HTTP response body extracted from the WARC record is the frozen raw body. For Wayback, the exact timestamped `id_` replay response body is the frozen raw body.

A discovered capture whose body cannot be frozen is recorded as `content_failure`; it is not downgraded to `no_capture`.

## V1 locator dependency

V2 must verify the exact v1 artifact ZIP digest and require exactly 64 unique locator rows before deriving URLs. It must also fail if any forbidden price/outcome key appears recursively in those locators.
