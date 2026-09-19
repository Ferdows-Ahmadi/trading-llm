# Prospective Live Source Routing v0.3 — Stage Exit

Experiment ID: `prospective-live-source-routing-v0.3`

This document records the frozen local custody anchors and closes the v0.3 prospective source-routing experiment. The cohort, acquisition artifacts, evidence packets, market snapshots, and forecast artifacts are closed to rerun, repair, replacement, evidence refresh, or forecast modification.

## Frozen execution state

- Selected markets: 12 from 12 distinct events.
- Structurally eligible rows: 154 across 38 eligible event groups.
- Forecast-ready acquisition rows: 10.
- Acquisition failure rows: 2 (`market_binding_failure`).
- Acquisition operational success: true (floor: 10).
- Direct resolution-source attempts: 10.
- Direct resolution-source successes: 8.
- Forecast-ready rows with identical Condition A / Condition B evidence: 2.
- Therefore 8 of 10 forecast-ready rows had genuinely augmented Condition B evidence.
- Outcomes accessed: false.
- Reserved holdout accessed: false.

## Forecast result and implementation failure

Condition A executed normally.

Condition B failed on the 8 rows where it required a second model call for the same market/question within the same model adapter instance. All affected cells ended as deterministic `model_failure_noop` records with:

`ResearchContractError: Duplicate residual decision for question '<question_id>'`

The root cause is implementation state reuse, not an evidence-size or model-capability failure:

1. each model reused one `OllamaMarketResidualV2Adapter` instance across Condition A and Condition B;
2. the adapter intentionally permits only one stored residual decision per `question_id`;
3. Condition A stored the first decision;
4. Condition B reused the same `question_id` and was rejected as a duplicate.

The two forecast-ready Condition B rows that succeeded were the rows whose Condition A evidence was verified empty, so Condition A did not call the model and did not occupy the adapter decision key.

This means v0.3 successfully tested the source-routing acquisition mechanism but did **not** produce a valid paired A-versus-B forecasting comparison on the 8 augmented rows.

The v0.3 summary's `operational_success=true` means every forecast-ready cell reached a protocol-defined terminal state, including `model_failure_noop`. It must not be interpreted as successful paired inference.

## Code and protocol

- Frozen preregistration commit: `6581cffba826c61548fba00eaf68d6ef57340dbe`
- Execution code commit: `b7c42b87eb55c52edd2d8550d13abbff5bbdddb2`
- Frozen preselection model manifest SHA-256: `440d3623c08082b724e5685975fdb1062a68e9796d9fbe1e20fabf5422667310`

Frozen local models:

- `llama3.1:8b` — `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`
- `qwen3.5:9b` — `sha256:6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`
- `deepseek-r1:8b` — `sha256:6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763`

## Local custody hashes

- `selection/selection-manifest.json`
  - SHA-256: `D9C8621563BCA17EB49CAB5A76D378AF431D479DDE1661AB00AB881D74B15364`
- `acquisition/acquisition-summary.json`
  - SHA-256: `E1107DC2DF3C9AC5E9390E03A4B1F94AACBC53A8B43069FCD73870E6B767C7C6`
- `forecast/forecast-summary.json`
  - SHA-256: `B1787372A125ADDF8DAF50B8318649E2A14AACF49C7756FB2ED6A1ADD2C8A4C1`
- Frozen archive: `trading-live-source-routing-v0.3-frozen.zip`
  - SHA-256: `6312DEF0C4C6E9F5CB413A2481922981462F02C6E16188E98D2C16760E5558C4`

## Closure rule

Do not rerun v0.3 selection, acquisition, Condition A forecasts, Condition B forecasts, model calls, source retrieval, or market snapshots. Do not replace the two acquisition failures. Do not overwrite or update the frozen ZIP.

Because the affected Condition B requests already reached the model path before the adapter rejected duplicate state, rerunning those cells after a code fix would violate the frozen one-request/no-retry rule. The paired forecasting question must therefore move to a new prospective cohort.

No v0.3 outcome lookup is needed to diagnose this implementation failure, and no outcome should be used to repair or reinterpret the failed paired comparison.

The next development lane is a separate v0.4 prospective experiment with isolated adapter state per model-condition pair and a stricter success metric that distinguishes terminal safety from successful paired inference.
