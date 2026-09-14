# ACD Fast Scalp v0.1 Validation Corpus

The validation corpus exists to test **strategy fidelity**, not profitability.

Each record is a trader/course-labeled example describing what the ACD method intended at a specific session and setup. These examples let us compare the implementation against the human method before historical profit testing begins.

## Scientific boundary

Do not add realized P/L, later price outcomes, or post-trade optimization notes to the canonical fidelity record.

The implementation is compared with the annotation first. If code and annotation disagree, record the mismatch and investigate it. Do not silently tune a rule until the example passes.

Outcome/backtest data belongs in separate replay/evaluation artifacts.

## Canonical machine-readable format

Schema:

```text
docs/market-strategy-lab/validation-corpus.schema.json
```

Record schema version:

```text
acd-validation-example-v0.1
```

Strategy version:

```text
acd-fast-scalp-v0.1
```

## Required identity and provenance

Every example records:

- stable `example_id`;
- instrument;
- regional ACD session;
- session date;
- source kind/reference;
- annotator/source identity;
- annotation timestamp;
- strategy/schema version.

A screenshot alone is not enough. The source reference should make it possible to recover the chart, course page, trader note, or data slice used for the annotation.

## Required strategy fields

Each record can hold:

- OR start/end/high/low;
- externally supplied A Up / C Up / A Down / C Down and source identity;
- previous trend;
- M15 direction;
- M5 direction;
- touched ACD boundary;
- momentum classification;
- confirmation mode/result and relevant candle timestamps;
- intended entry;
- main structural invalidation high/low;
- target;
- take / skip / unresolved decision;
- trader explanation;
- explicit unresolved fields.

## Unknown information

Unknown is a valid scientific state.

Use `null`, `unresolved`, or list the field in `unresolved_fields` as defined by the schema. Do not estimate an A/C level, invent a momentum threshold, or infer a structural stop merely to make a record look complete.

## Time discipline

All datetimes must be timezone-aware ISO-8601 timestamps.

The annotation should distinguish what was visible at the decision time from information added later by the annotator. The future replay engine must only consume information that existed at or before the replay decision timestamp.

## Human annotation workflow

1. Preserve the original chart/data reference.
2. Identify the regional session and OR.
3. Record the indicator's A/C levels exactly as shown.
4. Label previous trend from structure before the OR.
5. Label M15 and M5 direction.
6. Record the A/C boundary involved.
7. Label momentum as normal/weak, strong opposing, or unresolved.
8. Record confirmation mode/result and relevant M1 candles.
9. Record intended entry, structural invalidation and target only when the source supports them.
10. Record take/skip/unresolved and the trader's explanation.
11. List every missing or ambiguous rule in `unresolved_fields`.

## Corpus use

The corpus should be split conceptually into:

- implementation examples used while developing the formalizer;
- held-out fidelity examples used to check whether the frozen implementation generalizes to unseen trader annotations.

The held-out fidelity set is not the eventual profitability evaluation set. Those are separate experiments because humans apparently need multiple different ways to accidentally overfit things.
