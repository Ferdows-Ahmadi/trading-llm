# Prospective clustered forecaster v0.1 schema-binding clarification

Status: frozen after opening the already-authorized v0.3 cohort schema but before the first evidence-provider query and before any model forecast.

Parent preregistration commit: `d6f242b78a983bcd059384a68a5c05954dfc99f2`.

The parent protocol's canonical model question template uses semantic placeholders `{question}`, `{description}`, and `{end_date}`. Inspection of the immutable v0.3 `cohort.jsonl` established that the actual custody field names are:

- `{question}` -> `question_text`;
- `{description}` -> `description`;
- `{end_date}` -> `scheduled_end_at`.

All 77 selected rows contain non-empty values for `question_text`, `description`, and `scheduled_end_at`.

This clarification changes no cohort membership, evidence rule, discovery query, cutoff, model prompt wording, market probability, residual mapping, analysis rule, or stopping rule. It only binds the semantic placeholders in the already-frozen template to the actual immutable artifact schema.

The discovery query input specified as the exact frozen market question is therefore the exact `question_text` string. The model-facing problem statement is exactly:

```text
Market question:
{question_text}

Resolution criteria:
{description}

Scheduled market end:
{scheduled_end_at}
```

No evidence-provider query or model inference occurred before this binding was committed.
