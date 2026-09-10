# M4 Research Forecaster

This layer turns a verified frozen development dataset into timestamp-safe evidence,
strict structured forecasts, immutable artifacts, and an evaluation report. It is
research machinery only. The included deterministic fake adapter has no forecasting
skill and exists solely to exercise the offline pipeline.

## Boundaries

- Only a frozen CSV whose verified rows are explicitly marked `split=development` and
  its matching manifest are accepted by the runner; holdout rows fail closed.
- Evidence comes from a local JSON fixture. Every question must have an explicit entry,
  including questions with an intentionally empty evidence list.
- Every evidence item needs a timezone-aware `available_at` no later than the case's
  `source_cutoff_at`. Missing or unknown availability fails closed.
- Persisted evidence may record later operational provenance such as `retrieved_at`,
  archive references, content hashes, and packet hashes. Those fields are intentionally
  removed from the model-facing evidence projection so a historical model cannot infer
  post-forecast context from research operations performed later.
- Model metadata must explicitly assess the model as `historical-safe`, with both its
  release date and claimed knowledge cutoff no later than the earliest scored forecast.
  Unsafe metadata aborts the experiment before per-question execution begins.
- Blind requests omit market probability. Market-aware requests include only the
  sanitized contemporaneous probability, not its price timestamp.
- Outcomes and observed resolution timestamps never enter the adapter request.
- A failed forecast remains in `execution.total_questions` and is listed under
  `failures`; evaluation metrics use completed forecasts and report their sample size.

## Evidence fixture schema

```json
{
  "schema_version": 1,
  "questions": {
    "question-id": [
      {
        "source_id": "source-1",
        "source_type": "archived-document",
        "uri_or_reference": "archive://collection/item",
        "title": "Document title",
        "available_at": "2025-01-01T00:00:00Z",
        "retrieved_at": "2026-09-10T00:00:00Z",
        "text": "Historically available text"
      }
    ]
  }
}
```

`content_hash` may be included and is then verified. It is always present in the
constructed `EvidenceItem` and persisted packet. Operational provenance remains in the
persisted packet even though it is excluded from the prompt-facing evidence view.

## Development experiment CLI

```bash
prediction-lab-research \
  data/prediction-lab/polymarket-public-v0.1/development.csv \
  data/prediction-lab/polymarket-public-v0.1/development.manifest.json \
  evidence-fixture.json \
  data/prediction-lab/experiments/m4-smoke \
  --experiment-id m4-smoke \
  --hypothesis "The offline pipeline is deterministic; this is not an edge claim." \
  --prompt-version research-v0 \
  --mode blind \
  --validation-fraction 0.2 \
  --parent-group-column event_id \
  --repository-root ../..
```

The repository root is detected from the current directory when that option is
omitted. Pass it explicitly when invoking the command from outside the checkout.

Omit `--validation-fraction` to exercise the full development dataset. When supplied,
the runner evaluates only the newest inner validation segment after purging every
parent-event group already present in the inner development segment.

The output directory contains content-addressed evidence packets, forecast cache
entries, immutable forecast artifacts, explicit failure records, and canonical JSON
reports. A stable run identity includes code state, experiment configuration, model
metadata, evidence provider type, and the ordered evidence packet hashes. Each report
file itself is named by the hash of its complete report payload, so retries or changed
research inputs cannot collide with an earlier immutable report. Re-running identical
inputs resumes from cache and produces the same report bytes and path.

No command in this layer reads the frozen final holdout. A separate locked final
evaluation boundary remains intentionally unimplemented until a defensible pre-period
model and historical evidence source have been selected using development data only.
