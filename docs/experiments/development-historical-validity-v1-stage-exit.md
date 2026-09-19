# Development historical-validity audit v1 stage exit

Status: frozen after successful canonical historical-validity audit v1 and before any forecaster is run on the fresh 64-candidate cohort.

## Canonical audit result

The canonical audit is GitHub Actions run `34772413464`, artifact `historical-validity-audit-v1`, artifact ID `10322472038`, archive digest `sha256:fe675e33f2a403cf54a92aaa79cec45ed668758ce1139fc5b2348e601a55b930`, produced from code commit `26800b571d17eb560426eb4fb916433858b4d01e`.

It is bound to:

- candidate CSV SHA256 `6e6016ea64a4b9244ae0b4f23db962ee90d1297824418fe6272a4418bfa6ef21`;
- development CSV SHA256 `c05cbfa404804789faec779877c839b6655abc317217f182a673b2e91bd9f9a7`;
- canonical source-discovery artifact ID `10320984640`, digest `sha256:aee2e398b421bd8b2a94fbfd3f5edf2c6fb28c2b71f490e8a98c60ee3b8c7648`;
- adjudication protocol commit `e42d53029b41392c74281c9fa669fb7fc433ad32`;
- adjudication evidence commit `92f77c29817928c26eec6a6c6eaed13b0fd6e9ee`.

The frozen 64-case result is:

- A contract identity: 3 verified, 61 unknown, 0 contradicted;
- B outcome unknowability: 3 verified, 61 unknown, 0 contradicted;
- C authoritative final label: 3 verified, 61 unknown, 0 contradicted;
- overall: 3 `verified_valid`, 61 `unknown`, 0 `invalid`.

The three verified-valid question IDs are:

- `1068359` — Hyperliquid listed on Coinbase before 2027?
- `1251725` — Will Binance launch stock tokens in 2026?
- `1832174` — Another crypto hack over $100m by December 31?

All three canonical labels are Yes. The original candidate derivation remains event-independent by construction, so these three are also three distinct parent events.

No forecaster was run during the audit. The reserved holdout was not accessed by the audit.

## Adequacy decision

The verified-valid sample is **not adequate for a fresh model-versus-market validation experiment**.

This is a methodological stop decision, not a negative result about the forecaster. With only three independent cases, all with the same binary label, any Brier-score, log-loss, calibration, or residual-improvement estimate would be dominated by individual observations and would not support a credible claim of repeatable market edge. A confidence interval or paired bootstrap over three independent events would be largely decorative rather than informative.

Therefore:

1. `market-residual-v2` remains inactive on this cohort.
2. No LLM forecast is authorized on these 64 fresh candidates for the purpose of a confirmatory model-versus-market claim.
3. The three verified-valid cases are retained as audit successes, not promoted into a tiny confirmatory experiment.
4. The 61 unknown cases are not silently salvaged, reinterpreted using current metadata, or replaced after seeing their audit status.
5. The reserved holdout remains closed. The historical-validity shortfall is not a reason to spend the holdout.

## What the stage taught us

The main bottleneck is not candidate selection or outcome resolution. It is historical contract custody. The retrospective benchmark can supply many resolved market rows, but only a very small fraction of this fresh cohort could be defended with exact pre-forecast archived contract wording and rules under the preregistered standard.

Repeatedly expanding archive search after observing which historical cases are convenient would create a new adaptive-selection problem. The correct response is to change the data-collection design prospectively, not to lower the validity bar for this cohort.

## Authorized next stage

The next scientific stage is to preregister a **new prospective development-validation cohort** in which contract custody is created at collection time rather than reconstructed later.

Before any market is selected for that cohort or any model forecast is generated, the next protocol must freeze at least:

- market-universe source and query time;
- deterministic inclusion/exclusion rules;
- event-level independence rule;
- minimum sample / stopping rule determined without model outcomes;
- forecast timing rule that is prospectively executable and does not depend on actual future closure time;
- exact market-probability snapshot method;
- exact contract question, description, resolution rules, event/market IDs, and resolution-source locators frozen at forecast time;
- evidence cutoff and evidence-acquisition rules;
- model identity and leakage-safety rule;
- failure accounting and no-discretionary-replacement rule;
- outcome-resolution and authoritative-label procedure;
- paired model-versus-market metrics and dependence-aware uncertainty analysis;
- predeclared handling of unresolved/cancelled/ambiguous markets;
- explicit prohibition on reserved-holdout access.

The prospective cohort should be treated as development validation. It does not consume or reopen the existing reserved holdout.

## Holdout status

The reserved holdout remains reserved from adaptive forecaster evaluation. Nothing in this stage exit authorizes inspecting or scoring it.

## Stage exit

Historical-validity audit v1 is complete and frozen. Its scientifically valid conclusion is that the fresh historical cohort yields only three defensible cases and is insufficient for confirmatory forecasting evaluation. The next move is prospective custody-first data collection, not a three-case model run and not holdout opening.
