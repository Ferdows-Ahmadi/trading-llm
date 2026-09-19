# Prospective live multimodel v0.2 preselection gate

Status: frozen before any market-universe query for v0.2.

Experiment ID: `prospective-live-multimodel-v0.2`

This stage opens a new prospective development experiment after the successful v0.1 live-capture infrastructure pilot. It does **not** reuse, rerun, replace, or modify any v0.1 market, evidence packet, comparator, or forecast.

## Purpose

The v0.2 experiment will test two development questions on a fresh prospective cohort:

1. whether richer live evidence is operationally reliable when captured before the market comparator; and
2. how three frozen local models differ when given the exact same frozen evidence packet and market prior.

This is development research, not a confirmatory trading-edge claim.

## Preselection model set

The model tags are frozen now:

- `llama3.1:8b`
- `qwen3.5:9b`
- `deepseek-r1:8b`

Before any v0.2 market-universe query, the exact local Ollama digest for each tag must be frozen by the repository command `prediction-lab-freeze-models-v02`.

The resulting `model-manifest.json` and its SHA-256 must be recorded in a subsequent frozen v0.2 preregistration/amendment before market selection is authorized.

A missing tag, short/incomplete digest, registry failure, or later digest mismatch forbids v0.2 selection or inference. It is not permission to substitute a model.

## Planned cohort

The final v0.2 preregistration will freeze a fresh deterministic cohort of 12 markets from 12 distinct parent events, with a scheduled-end window of 7 to 30 days from the selection snapshot.

No market from the v0.1 pilot will be deliberately reused. Selection remains structural and deterministic, blind to evidence availability, model opinion, later price movement, and outcomes.

No v0.2 market may be queried before the exact model manifest is frozen and bound into the final v0.2 protocol.

## Planned evidence upgrade

The v0.1 Google News RSS capture remains the discovery layer because it completed reliably.

The v0.2 design will preserve the raw RSS response and first five unique provider-ordered items, then attempt live article enrichment for a fixed subset before the market snapshot. Article enrichment must be bounded, fully automatic, and frozen before the comparator. Per-item article retrieval failure may fall back to the already-frozen RSS item rather than failing the whole row; this rule will be specified exactly before selection.

No Common Crawl, GDELT historical reconstruction, Wayback lookup, or post-cutoff evidence recovery is permitted.

## Comparator and inference ordering

The final protocol will retain the successful v0.1 ordering:

1. freeze all evidence for a row;
2. only then acquire/freeze the Polymarket CLOB comparator;
3. only after acquisition has been attempted for the full cohort run any model;
4. give all three models the same frozen EvidencePacket and same market prior;
5. one request per model per evidence-bearing row;
6. deterministic prior no-op for verified-empty evidence;
7. record model failures without retries or substitution.

The exact residual mapping remains frozen unless a later preregistration explicitly changes it before selection.

## Leakage and custody boundary

Until the final v0.2 forecasts are frozen:

- no outcome lookup;
- no post-forecast market lookup for decision-making;
- no manual evidence selection or editing;
- no model substitution;
- no prompt adaptation from v0.2 outcomes;
- no discretionary market replacement;
- no reserved-holdout access.

The reserved 73-case holdout remains untouched.

## Authorization boundary

This document does **not** authorize a v0.2 market selection yet.

The only authorized next action is to freeze the exact three-model local Ollama manifest. After its digests and SHA-256 are recorded in the repository, the final v0.2 preregistration and implementation may be frozen. Only then may a fresh market universe be queried.
