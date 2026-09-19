# Research integrity engineering remediation

This change follows the engineering-only remediation scope at
`55af6da72d5edaf0493110428b7a2b9933524ae7`. It does not preregister or run an
experiment, revise a completed experiment, or authorize opening the reserved
holdout. Development outcomes were not used to choose these changes.

## Contracts

- `FileEvidenceProvider` computes the canonical SHA256 from the JSON object it
  actually loads. Frozen development runners supply the preregistered expected
  fixture hash on both validation and final loading. Whitespace is immaterial;
  source metadata, timestamps, IDs, bodies, and acquisition state are covered.
- The frozen-input downloader checks the GitHub artifact's unique numeric ID,
  run ID, expiry status, expected digest, and expected source commit when
  supplied. It downloads by numeric ID, verifies the ZIP bytes against the
  expected SHA256 before extraction, permits only explicit filenames, and
  refuses replacement, duplicate members, links, and path traversal. Missing
  reliable API digests are errors, not reasons to bypass verification. An
  adjacent identity receipt records the verified identity. No real download
  was used to validate this change; transport tests use synthetic archives.
- The existing model tag and digest are enforced before assigning the existing
  model provenance. This verifies the installed model identity reported by the
  local tooling; it does not independently establish its training corpus or
  eliminate hindsight contamination.
- Cached Wayback content is checked against its capture identity and locally
  stored raw/text SHA256. Archive/CDX digest metadata is not assumed to be the
  SHA256 of a replay HTTP body: those are different representations.

## Explicit evidence state

New acquisition/filter fixture output uses `schema_version: 2`. The existing
`questions` mapping is accompanied by an `availability` mapping with exactly
the same keys. Each state has `status` and a nonempty operational `detail`:

| Status | Meaning |
| --- | --- |
| `verified_complete` | The declared bounded acquisition completed; retained items exist. |
| `verified_empty` | The declared acquisition completed with no qualifying retained items. |
| `retrieval_failure` | At least one required attempted acquisition failed; partial evidence may exist. |
| `unknown_incomplete` | Acquisition completeness cannot be established, including missing or legacy records. |

“Complete” refers to the existing declared retrieval budgets, not an exhaustive
internet search or a judgment that evidence is informative. Budgets, source
selection, lexical thresholds, and ranking are unchanged. The acquisition ledger
preserves questions with missing/empty discovery; these records do not count as
attempted URLs. New checkpoint context hashes bind discovery settings and capture
settings to their inputs. Legacy checkpoints are not rewritten to claim verified
acquisition. Explicit failures and unknown states cannot reach model execution
or a cached forecast. A verified empty residual packet retains the exact market
probability without a model call. Relevance filtering propagates failure/unknown
states and converts verified acquisition with no retained items to verified empty.

State is included in new evidence packet hashes and excluded from model-facing
historical evidence. Existing schema-1 fixture/packet loading and completed
artifact hashes retain their legacy semantics. Newly deriving a fixture from
legacy evidence produces explicit unknown state, not retrospective verification.
Low-level legacy constructors remain available for compatibility; they do not
qualify for the new residual path.

## Inactive residual successor and binding

`market-residual-v2` is an explicitly versioned library request/adapter path. Its
user instructions request only the residual decision fields, matching the
existing residual system prompt and structured response schema. The v1 prompt,
system message, model selection, decoding settings, residual mapping, and delta
magnitudes are unchanged. No CLI or workflow selects v2. Scientific use requires
a separate preregistration and authorization; this change supplies neither.

V2 requires explicit verified acquisition state and its matching adapter. Its
schema-2 forecast artifact contains the canonical residual decision, included
in the artifact digest and held as immutable bytes in memory. The decision's
market prior, final probability, and citations must match the forecast fields.
Cache hits retain the embedded decision even when the adapter's transient ledger
is empty. Existing unbound v1 artifacts are not rewritten or silently upgraded.

## Offline reconciliation

The module below reads an explicitly supplied development CSV/manifest and only
the content-addressed files referenced by its supplied report. It requires an
independently known development CSV digest; it does not discover datasets or
enumerate experiment directories. Do not point it at reserved data.

```text
python -m prediction_lab.residual_reconciliation DEVELOPMENT.csv DEVELOPMENT.manifest.json RUN/reports/REPORT_HASH.json --expected-development-sha256 DEVELOPMENT_SHA256
```

For a previously completed unbound v1 run, also supply the explicit legacy
decision ledger with `--decisions DECISIONS.json --allow-legacy-unbound`.
That option reports `legacy_unbound` and cannot prove original decision-to-artifact
binding retroactively. Without it, unbound records fail reconciliation.

The tool independently implements the fixed logit mapping and scalar Brier/log
loss arithmetic; it does not call the production mapper or evaluator. It emits
every probability, per-question model/market loss contribution and difference,
aggregate losses, evidence-bearing/zero-evidence slices, action/strength counts
(including abstention), binding status, and evidence state. It validates the
report, config, model, benchmark, timestamps, exact question coverage, evidence
packet identity, citations, decision ledger, raw decision fields, and aggregate
report metrics. Malformed or inconsistent inputs fail rather than dropping rows.
No-op equality is exact; nontrivial floating-point reconciliation uses absolute
tolerance `1e-15`, and log loss uses the existing evaluator's `1e-15` endpoint
clipping. This tolerance is an arithmetic check, not a statistical decision rule.
Empty slices report null metrics. The current tool requires full cohort coverage;
it does not redefine existing partial-run scoring or inner-validation membership.

## Regression and verification scope

All additional tests use temporary synthetic cases, evidence, model responses,
archives, and reports. No completed v0.5 artifact, outcome, or reserved holdout
was needed. New regression files:

- `packages/prediction-lab/tests/test_artifact_integrity.py`: canonical fixture
  tampering; API identity, archive byte verification, safe extraction, model
  identity, frozen-input validation, and cached content tampering.
- `packages/prediction-lab/tests/test_evidence_availability.py`: state consistency,
  failure/unknown rejection, state hashing and historical projection, acquisition
  propagation, missing records, legacy checkpoints, and relevance propagation.
- `packages/prediction-lab/tests/test_residual_reconciliation.py`: every residual
  strength/direction, abstention, boundary/zero-evidence no-op, cache binding,
  mixed-cohort metrics/slices, ledger/context/artifact/report tampering, independent
  rejection of a consistently rehashed bad mapping, and explicit legacy handling.

Required checks are the complete Prediction Lab pytest suite, full-package Ruff,
and strict mypy for every changed/new production module. Mypy uses the package's
strict configuration and `--follow-imports=silent` to keep this scoped check from
being blocked by unrelated pre-existing modules. No mypy settings were weakened.
The broader package-wide mypy check was also compared against a source-only copy
of the starting commit; it is not a clean project-wide typing baseline.

Final local results (Python 3.12.13, pytest 8.4.2, Ruff 0.16.7, mypy 1.20.2,
pandas 2.3.3, NumPy 2.5.3, pandas-stubs 3.0.5.260730):

| Check | Result |
| --- | --- |
| `python -m pytest -q --disable-warnings` from the package directory | 184 passed; 291 NumPy/pandas timedelta deprecation warnings; 3.75 seconds. Warning display was suppressed, not the tests. |
| `python -m ruff check src tests` from the package directory | All checks passed. |
| Strict mypy, all 14 production files listed below, `--follow-imports=silent --config-file packages/prediction-lab/pyproject.toml` | Success: no issues in 14 source files. |
| Additional package-wide strict mypy | 21 errors in 10 unchanged files; source-only starting commit had 34 errors in 14 files. Normalized diagnostic comparison found no new errors. These unrelated typing issues were not suppressed or edited. |
| `git diff --check` | Passed. |
| Diff/AST review | Relevance constants and decision helpers unchanged; v1 residual adapter byte-equivalent; changes confined to the files below. No dataset, experiment artifact, preregistration, model provenance record, or workflow changes. |

The 76 added test cases are in the three new regression files above. Verification
used an isolated temporary environment outside the repository. No dependency
constraints or environment lockfiles in the repository were changed. CI was not
dispatched; the existing offline CI's full test and Ruff commands cover the new
regression files when that workflow is run separately.

## Exact changed files

Production files, all under `packages/prediction-lab/src/prediction_lab/`:

1. `artifact_identity.py` (new)
2. `commoncrawl_evidence.py`
3. `evidence.py`
4. `evidence_capture_stage.py`
5. `evidence_discovery_stage.py`
6. `evidence_relevance.py`
7. `gdelt_evidence.py`
8. `local_development_cli.py`
9. `research_forecaster.py`
10. `research_types.py`
11. `residual_development_cli.py`
12. `residual_reconciliation.py` (new)
13. `residual_v2.py` (new)
14. `wayback_content.py`

Other files:

15. `packages/prediction-lab/tests/test_artifact_integrity.py` (new)
16. `packages/prediction-lab/tests/test_evidence_availability.py` (new)
17. `packages/prediction-lab/tests/test_residual_reconciliation.py` (new)
18. `docs/research-integrity-remediation.md` (new; this report)

## Methodological findings intentionally left open

Engineering reconciliation does not demonstrate positive forecasting skill or
validate the completed v0.5 result. It does not resolve the small development
pilot, repeated development-set adaptation, uncertainty/calibration, evidence
coverage/relevance quality, retrospective title/source safety, model-weight
contamination, or the generalization of bounded residuals. Expanded development
design, sample size, frozen prompting/model choices, independent evaluation and
decision criteria, and the conditions for a single holdout opening require
separate methodological decisions and preregistration. No such choices were made
here. The reserved holdout remains closed. Existing experiment workflows and
preregistrations are unchanged; this remediation was not pushed or dispatched.
