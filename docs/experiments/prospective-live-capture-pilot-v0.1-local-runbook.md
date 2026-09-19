# Prospective live-capture pilot v0.1 local runbook

This runbook is operational guidance for the frozen v0.1 pilot protocol. It does not change the preregistration or operational clarification.

## Preconditions

Use the research branch only:

`research/prediction-market-lab-v0.1`

Before any live acquisition:

1. working tree must be clean;
2. install the prediction-lab package from the exact checked-out commit;
3. run the full test suite and Ruff;
4. start Ollama locally;
5. ensure `llama3.1:8b` is installed;
6. do not inspect outcomes, later prices, or the reserved holdout.

## Windows PowerShell example

From the repository root:

```powershell
git checkout research/prediction-market-lab-v0.1
git pull
$COMMIT = git rev-parse HEAD
python -m pip install -e ".\packages\prediction-lab[dev]"
pytest -q .\packages\prediction-lab\tests
ruff check .\packages\prediction-lab\src .\packages\prediction-lab\tests
```

Start Ollama in the normal local installation and confirm the frozen model exists:

```powershell
ollama list
```

The forecast phase will independently verify the exact model digest and refuse to run on a mismatch.

## Phase 1: freeze the structural pilot selection

Choose a new empty working directory. Example:

```powershell
$ROOT = "D:\trading-live-pilot-v0.1"
New-Item -ItemType Directory -Force $ROOT | Out-Null
prediction-lab-live-pilot-select "$ROOT\selection" --code-commit $COMMIT
```

This is the first live Polymarket-universe query for the pilot. The resulting `selection` directory is immutable. Do not rerun selection to obtain different markets.

## Phase 2: acquire evidence and post-evidence market snapshots

Begin immediately after selection. Every selected row must begin evidence acquisition inside the frozen 120-minute window.

```powershell
prediction-lab-live-session acquire `
  "$ROOT\selection\selected-candidates.jsonl" `
  "$ROOT\selection\selection-manifest.json" `
  "$ROOT\acquisition" `
  --code-commit $COMMIT
```

The acquisition phase performs no model inference. For each selected market it freezes live Google News RSS evidence first, then a CLOB bid/ask/midpoint snapshot, and enforces the 15-minute evidence-to-market binding window.

Do not delete or edit failed rows. No market replacement is allowed.

## Phase 3: run the frozen local Llama forecaster

Only after acquisition has been attempted for all eight rows:

```powershell
prediction-lab-live-session forecast `
  "$ROOT\acquisition" `
  "$ROOT\forecast" `
  --code-commit $COMMIT `
  --ollama-base-url "http://127.0.0.1:11434"
```

Before the first model request, the command verifies that `llama3.1:8b` matches the frozen digest. Model requests use the frozen 1200-second timeout. `verified_empty` rows are exact market-prior no-ops without a model call. Model failures are also frozen market-prior no-ops.

The pilot passes its infrastructure gate only if at least 7 of 8 rows produce terminal forecast records.

## Custody after the local run

Preserve the entire `$ROOT` directory unchanged. It contains raw Gamma responses, raw RSS, raw CLOB responses, evidence packets, bound market rows, model verification, forecasts, timestamps, and SHA-256 lineage.

Do not score or inspect outcomes during acquisition/forecasting. Outcome adjudication is a later separately controlled stage.
