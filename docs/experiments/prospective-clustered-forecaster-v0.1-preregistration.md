# Prospective clustered forecaster v0.1 preregistration

Status: frozen before manual inspection of selected v0.3 market semantics, before evidence acquisition for the selected cohort, and before any v0.3 model forecast is generated.

This protocol authorizes one **exploratory development** forecasting run on the completed prospective clustered custody v0.3 cohort. It does not authorize a confirmatory claim that the model beats the market and does not authorize access to the reserved 73-case holdout.

## Frozen cohort identity

The only permitted cohort is the canonical completed v0.3 custody artifact:

- custody protocol commit: `a4de3487a3c931b9e04578b7a501aabb6050e0cc`;
- custody stage-exit commit: `d7a1b75618d31839a1c7de2d3e2994073ca745a5`;
- acquisition workflow commit: `5bf128ebddb1fe82f578072beb2028545c824553`;
- GitHub Actions run: `34777066496`;
- artifact: `prospective-development-custody-v0.3`;
- artifact ID: `10323747083`;
- uploaded ZIP SHA256: `01eebf244add1ff21ee8d21257a000c5ee9588f751ae456e7fc7d17c0704a6aa`;
- selected cohort SHA256: `6c3cea364fd7548934a5e0e3e5a00cb45d1dd124318d9cf31ea0c012af661634`;
- selected rows: 77;
- selected parent-event clusters: 53;
- snapshot/source cutoff: `2026-09-13T19:14:39.226442Z`.

No row may be added, removed, substituted, re-ranked, or refreshed. Markets from the same parent event remain members of one analysis cluster.

## Forecast identity

Experiment identity: `prospective-clustered-residual-v2-v0.1`.

Only market-aware forecasts are generated. There is no separately tuned blind model in this experiment. The frozen contemporaneous CLOB midpoint in each custody row is the comparator and the prior supplied to the residual model.

For each row:

- `question_id = "polymarket-market:" + market_id`;
- `research_cutoff_at = source_cutoff_at` from custody;
- `forecasted_at = market_price_timestamp` from custody;
- `market_probability =` the frozen custody CLOB midpoint;
- `event_id` and `within_event_rank` remain analysis metadata and are not model features.

`research_cutoff_at` must be less than or equal to `forecasted_at`. No evidence with `available_at` later than `research_cutoff_at` may enter a model request.

### Canonical question text shown to the model

The model-facing question/problem statement is constructed exactly as:

```text
Market question:
{question}

Resolution criteria:
{description}

Scheduled market end:
{end_date}
```

where all three fields are taken from the frozen custody contract. Category, volume, liquidity, slug, event title, bid, ask, spread, later market prices, resolution state, and outcome are not supplied to the model.

The contract text is treated as the forecasting problem statement, not as external evidence.

## Timestamp-safe evidence acquisition

Evidence method identity: `gdelt-commoncrawl-prospective-v1`.

The evidence search uses no outcome, later resolution, model output, category, market probability, price direction, or post-cutoff semantic filter.

### Discovery

For every one of the 77 selected rows, use the exact frozen market `question` as the discovery query input to the existing deterministic `build_gdelt_query` logic in `prediction_lab.gdelt_evidence`.

Frozen discovery budget per row:

- source: GDELT DOC API;
- lookback: 90 days ending at the row's frozen `source_cutoff_at`;
- maximum GDELT records: 50;
- GDELT ordering: `datedesc`;
- only records with parsed `seendate <= source_cutoff_at` are eligible;
- duplicate URLs are removed deterministically while preserving newest-first GDELT order.

The GDELT result title/metadata is discovery metadata only. It is not by itself model evidence.

### Archived article admission

Starting from the GDELT results in newest-first order, attempt at most the first 8 unique article URLs per row.

For each attempted URL, use the existing exact-page `FastCommonCrawlClient` lookup and admit content only when all of the following hold:

1. the capture is from an eligible Common Crawl collection;
2. capture timestamp is `<= source_cutoff_at`;
3. GDELT `seendate` is `<= source_cutoff_at`;
4. archived response status is HTTP 200;
5. archived MIME contains HTML;
6. the captured page path matches the discovered article path under the existing exact-page variant logic;
7. capture digest has not already been admitted for that row;
8. extracted visible text is non-empty.

Frozen archive budget:

- maximum Common Crawl collections searched per URL: 3;
- maximum retained evidence items per row: 5;
- maximum extracted visible characters per item: 10,000.

Stop attempting further discovered URLs once 5 evidence items have been successfully frozen.

For an admitted item:

`available_at = max(Common Crawl capture timestamp, GDELT seendate)`.

That timestamp must be `<= source_cutoff_at` or acquisition fails closed.

The source ID remains content-addressed using the existing form `gdelt-cc:<crawl-id>:<capture-digest>`.

### No additional semantic relevance filter

No `lexical-relevance-v2` filter is applied to this broad prospective cohort. That historical filter only supports a narrow set of pilot question shapes and is therefore not a valid general-purpose gate here.

The frozen GDELT query plus exact pre-cutoff archived-page requirement is the acquisition gate. Evidence actionability is handled by the already bounded residual-v2 forecaster, which is instructed to abstain when evidence does not specifically justify moving the market prior.

No evidence item may be manually added, removed, reworded, summarized, or substituted after seeing its effect on a forecast.

## Evidence acquisition state and retries

Every selected row must end in exactly one explicit acquisition state:

- `verified_complete`: bounded acquisition completed and at least one evidence item was retained;
- `verified_empty`: bounded acquisition completed successfully but no qualifying archived evidence item was retained;
- `retrieval_failure`: at least one required attempted provider/archive operation failed;
- `unknown_incomplete`: completeness cannot be established.

Forecast execution is authorized only when **all 77 rows** are either `verified_complete` or `verified_empty`.

Engineering retries may retry only rows in `retrieval_failure`, using exactly the same query construction, cutoff, budgets, ordering, and archive rules. Successful/empty rows are immutable and are not re-searched for better evidence. No alternate evidence source may be introduced without a new preregistration committed before that source is queried.

The final evidence artifact must freeze raw/normalized discovery records, acquisition checkpoints, archived capture identities, extracted text, item hashes, acquisition states, evidence packets, configuration, code commit, this protocol commit, and aggregate status counts. Workflow logs may report counts/hashes/failures but must not print selected question text or evidence text.

Operational provenance fields such as retrieval timestamp, archive URI, capture hashes, and packet hash are persisted but excluded from model-facing evidence, following the existing `research_forecaster` projection.

## Frozen model

Provider/model: Meta Llama 3.1 8B Instruct via local Ollama.

Exact runtime model tag:

`llama3.1:8b`

Exact required model digest:

`sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`

Model-family provenance is `docs/models/meta-llama-3.1-8b-instruct-provenance.json`, which records a December 2023 knowledge cutoff with conservative upper bound `2023-12-31T23:59:59Z`.

Before forecasting, the workflow must pull/read the local model, inspect Ollama's installed model listing, and fail unless the digest matches exactly. The model must execute on a loopback Ollama endpoint with no browsing, external tools, retrieval, plugins, or network access from the model.

Frozen generation settings:

- prompt/adapter version: `market-residual-v2`;
- temperature: 0;
- seed: 0;
- streaming: false;
- one model request per evidence-bearing row;
- no prompt variants, self-consistency sampling, model ensembles, or candidate selection.

The residual-v2 system prompt, response schema, validation, and deterministic mapping are inherited unchanged from the existing `residual_adapter.py` / `residual_v2.py` implementation present before this preregistration.

## Frozen residual output contract

For a row with retained evidence, the model may not emit a probability or numeric adjustment. It emits exactly:

- `action`: `increase`, `decrease`, or `abstain`;
- `evidence_strength`: `none`, `weak`, `moderate`, or `strong`;
- non-empty `confidence_or_uncertainty`;
- non-empty `critique`;
- `cited_source_ids`, restricted to source IDs actually supplied in that row's evidence packet.

Valid action/strength pairs are:

- `abstain` + `none`;
- `increase` + `weak|moderate|strong`;
- `decrease` + `weak|moderate|strong`.

Duplicate citations receive only the existing deterministic duplicate-citation canonicalization. Unknown citations, unexpected fields, invalid combinations, malformed JSON, empty required text, or provider failure are model failures and are not silently repaired.

## Deterministic probability mapping

Mapping version remains `logit-residual-v1`:

- hard no-op / abstain: delta `0.00`;
- weak: absolute delta `0.25` log-odds;
- moderate: absolute delta `0.50` log-odds;
- strong: absolute delta `0.75` log-odds.

`increase` is positive and `decrease` is negative.

For market probability `p` strictly between 0 and 1:

`p_model = sigmoid(logit(p_market) + delta)`.

The model itself never chooses the numeric delta. No empirical tuning, rescaling, calibration fitting, or epsilon clipping is permitted before outcomes.

If `p_market` is exactly 0 or 1, a finite residual leaves it unchanged.

## Zero-evidence and failure behavior

### Verified empty evidence

A `verified_empty` row must not call the model. It is frozen as:

- action `hard_noop`;
- strength `none`;
- delta `0.0`;
- final probability exactly equal to the frozen market probability;
- empty citations.

### Model failure

Each `verified_complete` row receives exactly one model call. There is no retry to obtain a syntactically nicer or more favorable answer.

If that one call fails because of transport error, malformed response, schema violation, invalid action/strength combination, unknown citation, or any other residual contract failure, the row remains in the denominator and receives a deterministic conservative fallback:

- status `model_failure_noop`;
- delta `0.0`;
- final probability exactly equal to the frozen market probability;
- no claimed evidence direction or strength;
- the failure class/message is persisted separately from model-facing evidence.

Thus neither evidence scarcity nor model failure can improve results by deleting difficult rows.

## Forecast freeze and denominator

The forecasting stage must produce exactly 77 terminal forecast records, one for every frozen cohort row, consisting of model-evaluated residual decisions, verified-empty hard no-ops, or model-failure no-ops.

No outcome or post-cutoff market price may be fetched by the forecaster workflow. No scoring code is permitted in that workflow. The forecast artifact is frozen before prospective outcomes are known and records hashes of the cohort artifact, evidence artifact, model metadata, prompt version, code commit, and this protocol.

The workflow may print only aggregate forecast status/action/strength counts and artifact hashes. Per-market question text, evidence text, market prior, final probability, or semantic forecast output must not be printed to logs.

## Prospective resolution stopping rule

Cohort membership and forecast probabilities never change after the forecast artifact is frozen.

Resolution/scoring becomes eligible at the first of these two conditions:

1. all 77 selected markets have reached a terminal adjudication state; or
2. 90 days have elapsed after the latest frozen selected `end_date`.

At the stopping time, every row receives one adjudication status. No unresolved, cancelled, invalid, ambiguous, or unverifiable row is replaced.

Binary outcome hierarchy:

1. an unambiguous official Polymarket terminal Yes/No resolution for the exact frozen market;
2. if Polymarket's terminal record is unavailable but the frozen contract explicitly names a resolution source, an unambiguous result from that source;
3. otherwise `unverifiable` / non-adjudicable.

Cancelled/invalid markets are non-adjudicable rather than coerced to Yes or No.

Resolution evidence must be frozen with URLs/identifiers, retrieval timestamps, and hashes before scores are calculated.

If fewer than 40 distinct parent-event clusters contain at least one binary adjudicable row at the stopping time, no aggregate model-versus-market effect interpretation is authorized; only coverage/failure accounting may be reported.

## Frozen scoring rules

All outcome-based calculations are deferred until the prospective stopping rule is satisfied.

For each binary adjudicable row with outcome `y in {0,1}`:

- model Brier = `(p_model - y)^2`;
- market Brier = `(p_market - y)^2`;
- paired Brier difference = `model Brier - market Brier`;
- model and market log loss use the same endpoint clipping epsilon `1e-15` only for logarithm arithmetic;
- paired log-loss difference = `model log loss - market log loss`.

Negative paired differences favor the model. Positive differences favor the market.

### Primary exploratory estimand

Primary endpoint: **event-balanced paired Brier difference**.

For each parent event, average paired Brier differences across all binary adjudicable selected markets in that event. Then average those event means equally across adjudicable parent events.

A two-market parent event therefore receives the same total weight as a one-market parent event.

### Secondary estimand

Secondary endpoint: event-balanced paired log-loss difference, constructed identically by first averaging within parent event and then equally across events.

### Cluster uncertainty

Exploratory 95% uncertainty intervals use a parent-event cluster bootstrap:

- fixed bootstrap seed: `20260914`;
- 10,000 bootstrap replicates;
- sample adjudicable parent-event IDs with replacement;
- when an event is selected, carry all of that event's adjudicable selected rows together;
- recompute the event-balanced statistic for each replicate;
- report the 2.5th and 97.5th percentile bootstrap quantiles.

These intervals are descriptive/exploratory and do not convert v0.3 into a confirmatory study.

## Required diagnostics

The future outcome report must also include, without changing the primary estimand:

- total cohort rows and event clusters;
- binary-adjudicable rows and clusters;
- unresolved/cancelled/invalid/unverifiable counts;
- verified-complete versus verified-empty evidence counts;
- model-evaluated, hard-noop, abstain, and model-failure-noop counts;
- action and evidence-strength counts;
- row-level aggregate Brier and log loss for model and market, labeled descriptive because rows are clustered;
- row-level squared-error win/tie/loss counts versus market;
- event-balanced win/tie/loss counts using event mean Brier difference;
- leave-one-parent-event-out primary estimates for every adjudicable event;
- largest positive and negative single-event contributions to the primary estimate;
- results for within-event rank 1 versus rank 2 as descriptive diagnostics only;
- label balance;
- fixed ten-bin equal-width calibration tables for model and market when enough binary rows exist to populate bins, with empty bins retained as empty rather than merged post hoc.

No category-specific filtering, subgroup exclusion, prompt/model selection, residual-bound change, threshold tuning, or evidence-source change may be chosen after seeing v0.3 outcomes.

## Interpretation boundary

This is an exploratory development experiment. A favorable result may justify freezing a later independent confirmatory design, but cannot itself establish a deployable trading edge.

The existing reserved 73-case holdout remains sealed throughout evidence acquisition, forecasting, prospective waiting, and v0.3 analysis. Opening it requires a separate final-evaluation preregistration after all model/prompt/evidence decisions informed by v0.3 are complete.
