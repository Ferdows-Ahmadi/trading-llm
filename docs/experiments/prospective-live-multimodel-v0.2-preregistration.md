# Prospective live multimodel v0.2 preregistration

Status: **frozen after the preselection local-model identity freeze and before any market-universe query for v0.2**.

Experiment ID: `prospective-live-multimodel-v0.2`

Purpose: development experiment comparing three frozen local LLMs on the **same prospective evidence packets and the same frozen Polymarket priors**. This is not a confirmatory trading-edge test and does not authorize live-money trading.

The v0.1 live-capture pilot remains frozen and is not reused, repaired, rescored early, or extended.

## Preselection model freeze

The model-freeze stage completed at `2026-09-16T06:45:49.307561Z` before any v0.2 market selection.

Frozen model-manifest SHA256:

`296c91cbd22cd3d81b978f0c0a7499af8a54e9ecd8d76d20b8e6f2571691d40a`

Exact local Ollama identities:

1. `llama3.1:8b`
   - `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`
2. `qwen3.5:9b`
   - `sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`
3. `deepseek-r1:8b`
   - `sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763`

A missing tag or digest mismatch at forecast time forbids substitution. The affected model run fails operationally; no replacement model is permitted.

Because this experiment is prospective, model release-date/knowledge-cutoff metadata is descriptive only and is not used as a historical leakage gate. Scientific model identity is the exact tag + digest above.

## Cohort

Selection seed:

`prospective-live-multimodel-v0.2-selection-seed-2026-09-16`

Target: **12 markets from 12 distinct parent events**.

Scheduled-end window:

- minimum: selection snapshot + 7 days;
- maximum: selection snapshot + 30 days.

Reuse the v0.1 structural market criteria unchanged:

1. non-empty market ID, condition ID, question, and end date;
2. market not closed;
3. market active unless explicitly false;
4. order book enabled;
5. accepting orders;
6. exactly two outcomes normalized to Yes/No;
7. exactly two CLOB token IDs mapped one-to-one to outcomes;
8. exact parent event ID available;
9. scheduled end inside the frozen 7-to-30-day window;
10. volume >= 5,000;
11. liquidity >= 1,000;
12. non-empty description and at least one non-empty resolution-source locator.

Unknown or malformed fields fail eligibility. No topic/category or evidence-availability filter is allowed.

## Deterministic selection

Group structurally eligible rows by exact parent event ID.

Within each event, rank by lowercase SHA256 of:

`<selection-seed>|<event-id>|<market-id>`

Take the first ranked market per event.

Rank those event representatives globally by lowercase SHA256 of:

`<selection-seed>|multimodel|<event-id>|<market-id>`

Take the first 12.

No replacement is permitted after evidence, CLOB, model, or adjudication failure.

## Live evidence acquisition

The baseline provider remains Google News RSS search:

`https://news.google.com/rss/search`

Frozen locale:

- `hl=en-US`
- `gl=US`
- `ceid=US:en`

Query: exact Polymarket question text, unchanged.

RSS transport:

- at most 3 attempts;
- exponential backoff starting at 2 seconds;
- freeze successful raw RSS bytes before parsing;
- retain first 5 unique valid RSS items in provider order.

### Opportunistic full-article enrichment

To improve evidence quality without making the row depend on article-site reliability, the first **3** retained RSS items are eligible for deterministic enrichment in provider order.

For each of those items:

- request the RSS link directly with redirects enabled;
- at most 2 attempts;
- 20-second timeout per attempt;
- accept only successful `text/html` or `text/plain` responses;
- maximum raw response size used for extraction: 2 MiB;
- freeze successful raw response bytes and their SHA256;
- deterministically extract visible text locally;
- discard script/style/noscript content;
- normalize whitespace;
- use at most the first 8,000 visible characters;
- require at least 200 visible characters for enrichment to replace the RSS snippet text.

If enrichment fails, is blocked, is too short, is oversized, is non-text, or returns a non-success response, **the RSS item remains valid using its frozen title/snippet/source fields**. Enrichment failure therefore does not become row retrieval failure.

No manual URL substitution, source replacement, relevance re-ranking, browser search, GDELT, Common Crawl, Wayback, or post-capture browsing is allowed.

## Evidence state

- `verified_complete`: RSS completed successfully and at least one retained item exists, whether or not any article enrichment succeeded.
- `verified_empty`: RSS completed successfully with zero retained items.
- `retrieval_failure`: RSS provider/transport/XML/capture-window failure after the frozen retry policy.

Article-enrichment failures are recorded separately and never convert successful RSS evidence into `retrieval_failure`.

## Timing and market comparator

For each selected market:

1. begin RSS capture;
2. freeze RSS and parsed items;
3. attempt bounded article enrichment;
4. freeze final evidence packet;
5. acquire Yes-token CLOB best bid, best ask, and midpoint;
6. freeze raw CLOB responses;
7. require market timestamp >= evidence completion timestamp;
8. require the market snapshot no later than 15 minutes after evidence capture began.

Thus every model sees only evidence available no later than the frozen market comparator.

All 12 acquisition attempts must begin no later than **120 minutes after selection snapshot**.

All acquisition is frozen before any model inference begins.

## CLOB validity

Reuse the existing live-pilot rules:

- numeric bid, ask, midpoint;
- each strictly in `(0,1)`;
- `bid <= midpoint <= ask`;
- spread <= 0.10;
- midpoint alias handling unchanged;
- all three responses acquired in the same local session.

Invalid CLOB rows fail and are not replaced.

## Forecasting

Each forecast-ready row is evaluated independently by all three frozen models using:

- identical frozen market prior;
- identical frozen question, description, and resolution criteria;
- identical frozen EvidencePacket;
- identical `market-residual-v2` prompt family;
- temperature 0;
- seed 0 where honored by Ollama;
- one request per model per evidence-bearing row;
- no tools, browsing, retrieval, or cross-model communication.

Fixed residual mapping remains:

- abstain / none: `0.00` logit;
- weak increase/decrease: `+/-0.25`;
- moderate: `+/-0.50`;
- strong: `+/-0.75`.

A verified-empty row gives all models the exact market-prior deterministic no-op with no model call.

A single-model provider/schema/output failure gives only that model an exact prior no-op; it does not alter the other models' runs.

Model execution order is frozen as:

1. Llama 3.1 8B;
2. Qwen 3.5 9B;
3. DeepSeek-R1 8B.

The order has no effect on evidence or market snapshots because acquisition is already frozen.

Per-model timeout: 1200 seconds per request.

## Operational gates

Acquisition succeeds operationally if at least **10 of 12** selected rows become forecast-ready.

The forecasting stage succeeds operationally if every forecast-ready row has a terminal record for all three frozen models, where terminal means:

- `model_evaluated`;
- `model_failure_noop`; or
- `verified_empty_noop`.

These gates qualify infrastructure only. They do not constitute predictive success.

## Pre-resolution diagnostics

After all forecasts are frozen, the following outcome-blind diagnostics are allowed:

- action counts by model;
- evidence-strength counts by model;
- citation counts;
- pairwise model agreement/disagreement;
- magnitude and direction of residual movement;
- article-enrichment success/failure counts;
- model runtime and schema-failure counts.

No tuning may use future outcomes from these rows.

## Later adjudication and scoring

After market resolution, compare each model separately against the same frozen market prior using:

- paired Brier difference: model minus market;
- paired log-loss difference: model minus market;
- descriptive per-model win/loss/tie counts versus market;
- pairwise model comparisons as development diagnostics only.

With 12 events, no confirmatory edge claim is authorized.

Rows unresolved 30 days after scheduled end are marked unresolved for primary accounting and are not replaced.

## Holdout boundary

The reserved 73-case holdout remains untouched.

Nothing in v0.2 authorizes opening, scoring, filtering, tuning to, or otherwise adapting against that holdout.

## Prohibited before all v0.2 forecasts are frozen

- outcome lookup;
- post-forecast market-price lookup for model decisions;
- model substitution;
- manual evidence editing or source substitution;
- topic/category selection after seeing evidence;
- prompt/residual tuning based on v0.2 outcomes;
- market replacement;
- use of the reserved holdout;
- use of v0.1 eventual outcomes, if they become available during v0.2 acquisition, to alter v0.2 behavior.
