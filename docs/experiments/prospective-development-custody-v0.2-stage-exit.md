# Prospective development custody v0.2 stage exit

Status: closed as a completed but inadequate development-validation custody cohort. No forecaster run is authorized from v0.2.

Canonical protocol commit: `12a39fcc156ace92356e3d6b05b7a444f6c23679`.

Canonical acquisition workflow commit: `42aaaa4833f906a821de3d790ff32ff23e7a0274`.

Canonical GitHub Actions run: `34776591966`.

Canonical artifact: `prospective-development-custody-v0.2`, artifact ID `10323322554`, uploaded ZIP SHA256 `0cce41fd5f967e34e126d382ce6fbbf7a2117f36d7a25dec59142d75ffa03ae2`.

## Completed custody result

The run completed the frozen pre-live contract checks, live keyset acquisition, CLOB acquisition, deterministic selection accounting, and immutable artifact upload.

Aggregate result:

- snapshot reference: `2026-09-13T19:05:25.078578Z`;
- Gamma keyset pages: 430;
- universe rows: 42,908;
- structurally eligible markets: 161;
- deterministic parent-event groups / first representatives: 52;
- CLOB-valid first representatives: 48;
- CLOB transport failures: 0;
- rejected first representatives: 4, comprising 3 `invalid_clob_price` and 1 `spread_above_maximum`;
- selected rows: 48;
- selected parent-event groups: 48;
- custody adequate for forecaster preregistration under v0.2: **false**;
- cohort SHA256: `e1e4ea91d2dd7d5e835869349264450b9d6bfac2b7e08fd53011b387784304bc`;
- selection-ledger SHA256: `d7893e0f049de16077f505769aee5aac45897814f24e67b3b2b28e7da34862aa`;
- universe SHA256: `88f2156de6b4090a7ecca0537741f9f4bd0c89beb07a3a2a46dff388bba13a71`.

The midpoint alias correction succeeded operationally: 48 of 52 deterministic first event representatives passed the frozen CLOB gate. The remaining inadequacy is therefore not the v0.1 midpoint-schema failure.

## Blinded recruitment diagnosis

After the canonical artifact was frozen, a diagnostic read was restricted to `selection-ledger.jsonl`. No question text, description, category/topic, slug, selected probability, bid/ask/midpoint numeric value, outcome, model output, or reserved-holdout content was inspected.

The 161 structurally eligible markets were distributed across 52 anonymous parent-event IDs as follows:

| Eligible markets in event | Number of events |
| ---: | ---: |
| 1 | 24 |
| 2 | 10 |
| 3 | 5 |
| 4 | 5 |
| 6 | 3 |
| 7 | 1 |
| 8 | 1 |
| 9 | 1 |
| 19 | 1 |
| 21 | 1 |

Thus 28 of 52 parent events contained at least two structurally eligible markets, and 18 contained at least three. The median eligible markets per event was 2, mean approximately 3.10, and maximum 21.

Under an anonymous cap of at most two structurally eligible deterministic representatives per parent event, the same event-size structure would contain at most 80 candidate markets before CLOB validation. A cap of three would contain at most 98. These are recruitment diagnostics only; they do not retrospectively alter v0.2 membership.

Structural rejection counts across the full 42,908-row universe were also inspected only as reason-code aggregates:

- `volume_below_minimum`: 40,071 rows;
- `liquidity_below_minimum`: 33,923;
- `not_binary_yes_no_with_two_tokens`: 18,272;
- `missing_resolution_source`: 13,568.

Rows rejected for exactly one structural reason were dominated by `missing_resolution_source` (2,197) and `volume_below_minimum` (895), with 65 liquidity-only and 17 binary-token-only failures. Thresholds are not relaxed in v0.2 after observing these counts.

## Interpretation

Extending the scheduled-end horizon from 45 to 90 days increased the queried universe from the v0.1 total of 33,010 rows to 42,908 rows, but the number of deterministic parent-event groups remained 52. The principal recruitment bottleneck for the frozen rules is therefore parent-event independence / within-event concentration, not merely the maximum horizon and not CLOB transport.

v0.2 is permanently closed with 48 selected event-independent cases. It must not be rerun, supplemented, or reinterpreted as satisfying its preregistered 60-case adequacy floor.

## Next-stage boundary

Any design that admits more than one market from a parent event is a new clustered development design and must be preregistered before a fresh live query. Such a cohort must not treat markets from the same parent event as independent observations. Event-cluster-aware scoring, uncertainty, deletion sensitivity, and concentration diagnostics must be frozen before any model forecast is produced.

The existing reserved 73-case holdout remains untouched and is not authorized for adaptive model development.
