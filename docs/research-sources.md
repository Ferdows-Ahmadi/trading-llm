# Historical Research Sources

## Primary source for v0.1

Repository: `Jon-Becker/prediction-market-analysis`

Pinned upstream revision:

```text
2276382cb616107db8c8647803bffa4a0d7091f8
```

The source repository is MIT licensed. We do not vendor its large historical dataset
into this repository. Local research runs should obtain the upstream Parquet data and
record the pinned source revision in every frozen-dataset manifest.

## Adapter boundary

The translation code lives in:

```text
packages/prediction-lab/src/prediction_lab/adapters/jon_becker.py
```

It accepts pandas DataFrames shaped like the upstream Parquet tables and emits the
Prediction Market Lab forecast-case contract. This keeps upstream blockchain/exchange
schema details out of the evaluator.

## Kalshi mapping

The initial adapter uses finalized binary markets and trade executions:

- `ticker` -> `question_id`
- `title` -> `question_text`
- trade `created_time` -> forecast/market-price timestamp
- `yes_price / 100` -> contemporaneous YES market probability
- finalized `result=yes|no` -> binary outcome
- resolved market `_fetched_at` -> conservative resolution-observed timestamp when
  available, falling back to close/end fields

A benchmark later samples one eligible observation per resolved question rather than
allowing high-volume questions to dominate merely because they generated more trades.

## Polymarket mapping

The CTF trade table contains block numbers rather than a direct event timestamp, so the
adapter requires the upstream block-number -> timestamp table.

For a CTF `OrderFilled` row:

- if `maker_asset_id == 0`, the maker supplied USDC and the traded outcome token is
  `taker_asset_id`; token price is `maker_amount / taker_amount`;
- if `taker_asset_id == 0`, the taker supplied USDC and the traded outcome token is
  `maker_asset_id`; token price is `taker_amount / maker_amount`;
- rows without USDC on either side are excluded from this initial adapter;
- `clob_token_ids`, `outcomes`, and terminal `outcome_prices` from the resolved market
  identify the YES/NO token and final binary outcome;
- a YES-token trade at price `p` maps to YES probability `p`;
- a NO-token trade at price `p` maps to YES probability `1 - p`.

Only binary markets whose outcomes can be identified exactly as YES and NO are accepted
in v0.1. Terminal outcome prices must indicate a clear resolution (approximately 1/0 or
0/1). Ambiguous, unresolved, malformed, or non-binary markets are skipped.

When several fills map to the same question and exact timestamp, one deterministic final
snapshot is retained using `log_index` when available. This avoids multiplying the
statistical weight of a question because several fills occurred within one timestamp.

## Resolution timestamp policy

The evaluator needs the outcome as a label, but a historical forecasting case must have
been created before that outcome was knowable. For the initial adapter we prefer the
resolved market row's `_fetched_at` timestamp as a conservative `resolved_at`, because
that is a point at which the final result is known to have existed in the upstream
snapshot. If unavailable, venue close/end timestamps are fallbacks.

This is intentionally conservative and should be revisited if the upstream dataset later
provides a verified settlement timestamp.

## Benchmark sampling policy

The default planned benchmark policy is:

1. translate all usable historical market/trade rows into forecast cases;
2. select the latest available market observation no later than a fixed lead time before
   resolution (initial experiment: 7 days);
3. retain exactly one case per resolved question;
4. split development and holdout sets strictly by forecast timestamp;
5. freeze each dataset with a SHA-256 manifest containing the exact source revision and
   selection policy.

The lead time is an experiment parameter, not a hidden optimization knob. If multiple
lead times are studied, they must be reported as separate experiments and the final
holdout must not be used to choose among them.
