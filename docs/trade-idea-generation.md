# Explainable Trade Idea Generation

## Scope
- Deterministic trade thesis generation from:
  - technical analysis outputs
  - setup detections
  - score breakdowns
  - news/context feed
- No LLM dependency.
- No certainty claims; confidence is bounded and uncertainty is explicit.

## Output guarantees
Each generated thesis includes:
- setup direction
- supporting factors
- contradictory factors
- invalidation level/condition
- confidence label + numeric score + explanation
- informational disclaimer

## Endpoint
- `POST /api/v1/trade-ideas/generate`

## Example response
See: `docs/samples/trade-idea-sample.json`.
