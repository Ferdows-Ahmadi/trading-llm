# Prospective live-capture pilot v0.1 stage exit

Status: frozen after successful local acquisition and forecasting, before any outcome lookup or scoring.

Experiment ID: `prospective-live-capture-pilot-v0.1`

This stage exit binds the completed live pilot to the preregistration and operational clarification already frozen on the research branch. It records the local immutable custody anchors supplied after the pilot completed.

## Frozen code and protocol identities

- execution code commit: `c7a9f2d48ff2338f492769ba246912744f8a90d5`
- preregistration commit: `6bf0f71bb18641a5baf81764e41277bc00c3faa1`
- operational clarification commit: `ab8bafa7bdd3ab9adea300278ac58f53f6d4ec4d`
- model tag: `llama3.1:8b`
- required model digest: `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`

The local worker verified the exact model digest before forecasting.

## Selection result

The live selector froze:

- universe rows: 32,115
- structurally eligible rows: 165
- eligible parent-event groups: 44
- selected rows: 8
- selected parent-event groups: 8
- target cohort: 8
- selection snapshot reference: `2026-09-16T06:08:40.671488Z`
- evidence accessed during selection: false
- model forecast run during selection: false
- outcomes accessed during selection: false
- reserved holdout accessed during selection: false

Selection-manifest SHA256:

`b68fe662d21b56e29a94c25936c9d0c85aaa86022f14b43390a58984d9257cc3`

## Acquisition result

Acquisition attempted all eight frozen rows before model inference.

Result:

- `forecast_ready`: 7
- `market_binding_failure`: 1
- model forecast run during acquisition: false
- outcomes accessed: false
- reserved holdout accessed: false

The single failed row is:

- market ID: `3008512`
- event ID: `727186`
- status: `market_binding_failure`
- reason: `Invalid CLOB snapshot: invalid_clob_price`

The row was not replaced, repaired, or re-acquired after observing the failure.

Acquisition-summary SHA256:

`85067d8fc2e399dc7a4c2513c8587606742767be837602bd39ce451dcc20d493`

## Forecast result

The frozen forecast session completed with:

- rows accounted for: 8
- terminal forecast rows: 7
- operational success floor: 7
- operational success: true
- `model_evaluated`: 6
- `verified_empty_noop`: 1
- `acquisition_failure_no_forecast`: 1
- outcomes accessed: false
- reserved holdout accessed: false

The verified-empty row received the exact market-prior no-op without a model call, as preregistered.

The acquisition-failure row received no model forecast and remains in accounting, as preregistered.

Forecast-summary SHA256:

`505885face41247f076f3b5ec36934a38e3b82715e4c8db2eeab8619a21d3f96`

## Frozen local archive

A local immutable archive was created after selection, acquisition, and forecast completion.

Archive filename:

`trading-live-pilot-v0.1-frozen.zip`

Archive SHA256:

`405de18f19a3136afdbaa37a9cd4e303730cc4e0658ba693e26399c7aeed597a`

This digest is the custody anchor for the complete local pilot directory as frozen after forecasting.

## Scientific interpretation

The pilot **passed its operational objective**. The new architecture successfully completed deterministic market selection, live evidence capture, post-evidence market snapshot binding, exact-model verification, local inference, immutable row accounting, and local artifact freezing without accessing outcomes or the reserved holdout.

This result does **not** establish forecasting edge. The preregistration explicitly classifies this as an operational pilot, and with only eight distinct events no confirmatory model-versus-market claim is authorized.

The pilot also revealed substantive model/evidence behavior worth studying later, including cases where the model increased probability despite weak or indirect evidence. Those observations may motivate a new development protocol, but they must not alter the forecasts frozen in this pilot.

## Frozen boundary after forecasting

The following are prohibited for this completed pilot:

1. rerunning selection to obtain more convenient markets;
2. rerunning acquisition to repair the failed CLOB row;
3. refreshing or replacing evidence;
4. changing the model, prompt, residual mapping, or frozen probabilities;
5. using post-forecast market prices to alter any frozen forecast;
6. inspecting outcomes before the authorized adjudication stage;
7. touching the reserved 73-case holdout.

The current forecast records are final for this pilot.

## Authorized next stage

For this exact pilot, the only authorized scientific continuation is later outcome adjudication and debugging-only scoring under the frozen preregistration after markets resolve.

Separately, a new development experiment may be preregistered before any additional live acquisition. Candidate topics include model comparison and evidence-quality improvements, but any such work must use a new experiment identity and must not modify this pilot.

## Stage exit

Prospective live-capture pilot v0.1 is complete and frozen at the forecasting stage. Its operational result is successful at 7 of 8 terminal forecast rows. No outcome has been accessed, no scoring has been performed, and the reserved holdout remains untouched.
