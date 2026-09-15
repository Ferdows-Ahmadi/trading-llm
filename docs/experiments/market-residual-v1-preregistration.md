# Market-Residual Forecaster v1 Preregistration

Status: preregistered before implementation and before any residual-v1 model output is generated.

## Purpose

The clean relevance-v2 development run showed that a stricter deterministic evidence gate removed most low-quality evidence and moved the market-aware development score from worse than the market to slightly better on the frozen 20-question pilot. Only four pilot questions retained evidence, so the next experiment changes exactly one substantive component: how the market-aware forecaster converts evidence judgment into a probability.

This experiment does not tune against the 20 observed outcomes. It tests a fixed, conservative market-residual architecture chosen before implementation.

## Frozen inputs

The experiment must use exactly:

- development pilot workflow run `34555783305`;
- development artifact `prediction-lab-development-pilot-v0.1`;
- development dataset SHA256 `d27e2b84cf1f3bc9bdeb4904e15791aad5d2e586685b7f32ab1647d15eee41ce`;
- canonical relevance-v2 evidence specification `docs/experiments/evidence-relevance-v2-canonical.json`;
- relevance-v2 fixture SHA256 `cfafa8c780c7067c656a5c8474f172f46239f12e10f1632cd22256f2430a3035`;
- exact Ollama model tag `llama3.1:8b`;
- exact model digest `sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`;
- Meta Llama 3.1 8B Instruct historical-safety provenance already checked into the repository.

The 73-question holdout remains sealed and must not be downloaded, opened, scored, or used for any decision in this stage.

## Controlled comparison

The blind mode remains the existing direct-probability `research-v0` forecaster as a control.

Only market-aware mode changes. Its prompt/adapter version is `market-residual-v1`.

No model change, evidence change, benchmark change, or relevance-rule change is permitted in the residual-v1 run.

## Zero-evidence rule

If a question has zero retained evidence items, the residual adapter must not call the model.

It must deterministically set:

- residual action: `hard_noop`;
- logit delta: `0.0`;
- final probability: exactly the contemporaneous market probability;
- cited source IDs: empty.

This is a hard code path, not a prompt preference.

## Evidence-bearing model output

For a question with one or more retained evidence items, the model may not emit a final probability.

It must emit only a constrained residual decision with these semantic fields:

- `action`: one of `increase`, `decrease`, `abstain`;
- `evidence_strength`: one of `none`, `weak`, `moderate`, `strong`;
- `confidence_or_uncertainty`: non-empty text;
- `critique`: non-empty text;
- `cited_source_ids`: unique IDs drawn only from the supplied evidence packet.

Valid combinations are:

- `abstain` with strength `none`;
- `increase` with strength `weak`, `moderate`, or `strong`;
- `decrease` with strength `weak`, `moderate`, or `strong`.

Any other combination is a contract failure. Unknown citations and malformed output remain failures; they are not silently repaired except for the already-established deterministic duplicate-citation canonicalization.

## Deterministic residual mapping

The mapping is fixed before implementation:

- `abstain` / `none` -> delta `0.00`;
- `weak` -> absolute delta `0.25` log-odds;
- `moderate` -> absolute delta `0.50` log-odds;
- `strong` -> absolute delta `0.75` log-odds.

`increase` uses a positive delta and `decrease` uses a negative delta.

The maximum absolute adjustment is therefore preregistered at `0.75` log-odds. No empirical tuning of this bound or the three strength levels is allowed on this 20-question pilot.

For market probability `p` strictly between 0 and 1:

`logit(p_final) = logit(p_market) + delta`

and `p_final` is the sigmoid of that value.

If the market probability is exactly 0 or exactly 1, the finite residual leaves that boundary probability unchanged. No epsilon clipping is introduced.

The deterministic mapping, not the LLM, produces the scored final probability.

## Artifact requirements

For residual market-aware forecasts:

- `base_rate_probability` records the market probability;
- `updated_probability` and `final_probability` record the deterministic residual result;
- raw structured output must preserve the residual action, strength, signed logit delta, mapping version, market probability, and whether the result was a hard no-op;
- final probability must be reproducible from the persisted residual metadata and market probability.

## Evaluation

The run must retain all 20 development questions in the denominator and require 20/20 successful forecasts for both blind and market-aware modes before scientific interpretation.

Primary comparisons on the identical 20 questions:

- Brier score versus the contemporaneous market;
- Brier skill versus market;
- log loss versus market;
- expected calibration error versus market;
- per-question squared-error win rate versus market.

Required diagnostics:

- the four relevance-v2 evidence-bearing questions versus the sixteen zero-evidence questions;
- action counts for `increase`, `decrease`, `abstain`, and `hard_noop`;
- strength counts for `weak`, `moderate`, and `strong`;
- signed and absolute logit deltas;
- per-question probability movement from market;
- direction correctness for evidence-bearing adjustments;
- identification of any question dominating excess gain or loss.

## Decision rule after the run

This pilot is still development-only. A positive aggregate result does not justify opening the holdout because only four current questions carry retained evidence.

After residual-v1, the next methodological decision must be based on whether the constrained architecture behaves sensibly and whether its apparent edge survives a substantially expanded development set. The residual bound and mapping must not be retuned against these 20 outcomes.
