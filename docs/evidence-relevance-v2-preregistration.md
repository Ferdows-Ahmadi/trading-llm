# Evidence Relevance v2 Preregistration

Status: preregistered before implementation and before inspecting v2 pilot outcomes.

## Purpose

The v0.3 development pilot showed that the market-aware forecaster's meaningful excess loss was concentrated in the subset with retained historical evidence, while zero-evidence questions were already effectively market no-ops. The next development change therefore isolates one variable only: the deterministic relevance gate that decides which frozen historical articles are retained as evidence.

This stage does not change the model, prompt, market-aware forecasting contract, probability-generation method, frozen benchmark, forecast timestamps, outcome labels, or holdout policy. The 73-question holdout remains sealed.

## Method identity

Method version: `lexical-relevance-v2`.

The v2 gate is deterministic, label-blind, outcome-blind, and contains no LLM, embedding model, learned semantic classifier, or outcome-derived threshold.

## Preregistered structural rules

An evidence item is eligible only when all applicable rules below pass.

1. **Aboutness prominence.** The question subject must appear either in the article title or in the first 40 whitespace-delimited words of the article body.
2. **Intent proximity.** At least one intent signal for the question type must occur within a fixed 50-word window on either side of a subject mention. Intent vocabularies remain question-shape-specific and are declared in code.
3. **Repeat-subject requirement for non-title items.** If the subject does not appear in the title, it must appear at least twice in the article body. This is intended to reject incidental one-line mentions without requiring an outcome-aware score.
4. **Roundup/listicle exclusion.** Items whose titles match an explicitly declared deterministic roundup/listicle pattern are rejected. The pattern family is limited to generic list/roundup constructions such as `top N`, `N ... to watch`, `weekly roundup`, `daily roundup`, `market roundup`, `crypto roundup`, and `key crypto updates`.
5. **No weighted relevance score.** Passing is conjunctive rather than based on a tunable summed score. Ranking among already-passing items may use deterministic non-outcome metadata only.
6. **Existing deduplication remains.** Exact content-hash duplicates and normalized duplicate titles remain excluded, and the existing per-question item cap remains unchanged.

## Fixed parameters

- lead window: 40 body words
- intent proximity radius: 50 words on each side of a subject mention
- minimum body subject mentions when title lacks subject: 2
- maximum retained items per question: 5

These values are fixed before implementation. They will not be changed in response to the outcomes of the 20-question rerun.

## Audit requirements

The relevance audit must record enough information to explain every keep/reject decision, including at minimum:

- whether the subject appeared in the title
- subject mention count in the body
- whether the subject appeared in the lead window
- matched intent signals
- whether a roundup/listicle pattern matched
- final keep/reject reason

## Evaluation plan

After implementation and tests, regenerate the evidence fixture from the same frozen 94-item Wayback corpus and the same 20 development questions. Freeze the resulting artifact and hash. Then rerun the exact same Llama 3.1 8B development experiment with:

- exact model artifact digest unchanged
- prompt `research-v0` unchanged
- blind and market-aware modes unchanged
- same 20 development questions
- holdout inaccessible

The purpose of that rerun is attribution: any change in behavior should be attributable to the relevance gate rather than a simultaneous forecasting-architecture change.

## Non-goals for this stage

The following are explicitly deferred until after the relevance-only rerun:

- logit-residual forecasting
- a new prompt version
- abstention/evidence-actionability output
- evidence-strength weighting
- source-agreement weighting
- model replacement
- bound tuning
- holdout access

## Anti-overfitting rule

The structural rules above are specified before implementation. After the v2 rerun, they are not to be altered merely because a particular known development example was helped or harmed. Any later relevance-method revision must receive a new version and a new preregistration before execution.
