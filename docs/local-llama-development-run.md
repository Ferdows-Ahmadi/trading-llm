# Local Llama 3.1 8B Development Run

This is the operator handoff for the first real-model development experiment. It is not a
holdout run and it is not a trading/profitability claim.

## Frozen experiment inputs

- Repository: `Ferdows-Ahmadi/trading-llm`
- Branch: `research/prediction-market-lab-v0.1`
- Local-run implementation commit: `cf5110cf252143fb7134a750fef87ecf95aad869`
- Prediction Lab CI for that commit: workflow run `34558956074`, success, 94 tests passed,
  Ruff clean.
- Hosted deterministic forecast smoke was revalidated successfully on workflow run
  `34558743457` before the final lint-only runner fix.
- Development pilot: workflow run `34555783305`, artifact
  `prediction-lab-development-pilot-v0.1`, 20 development-only questions.
- Filtered historical evidence: workflow run `34529685281`, artifact
  `evidence-relevance-filter-v0.1`, 16 kept evidence items across 8 questions and 12 explicit
  zero-evidence questions.
- Model: Meta Llama 3.1 8B Instruct through local Ollama tag `llama3.1:8b`.
- Checked-in knowledge cutoff: `2023-12-31T23:59:59Z`.
- Checked-in release date: `2024-07-23T00:00:00Z`.
- Frozen pilot forecast timestamps run from 2025-10-16 through 2026-04-15, after the model
  release and cutoff.

The 73-case event-independent holdout remains sealed. The local runner downloads only the
fixed development-pilot and filtered-evidence artifacts named above and fails if any
`holdout*` file appears in its inputs.

## Windows run procedure

Run these commands from the repository root in PowerShell after Ollama is running locally
and GitHub CLI (`gh`) is installed and authenticated:

```powershell
git checkout research/prediction-market-lab-v0.1
git pull --ff-only
py -3.12 -m pip install -e ".\packages\prediction-lab[dev]"
gh auth status
ollama list
py -3.12 -m prediction_lab.local_development_cli
```

The module form is preferred on Windows because it does not depend on the Python Scripts
directory being on `PATH`. The installed console command `prediction-lab-local-development`
is equivalent.

If `llama3.1:8b` is not already installed, the runner invokes `ollama pull llama3.1:8b`.
Ollama itself must already be running so the runner can read `/api/tags` and freeze the exact
local model digest before inference.

## What the runner enforces

The runner refuses to score unless the checkout is clean and on the research branch. It
keeps inputs and outputs outside the Git checkout, accepts only a loopback Ollama endpoint,
verifies the exact frozen development dataset and relevance-filter identities, freezes the
local Ollama digest as `immutable_version`, builds historical-safety metadata from the
checked-in Meta provenance, and rechecks both the Git commit and model digest while the run
is in progress.

It executes `blind` first and then `market-aware`, both with prompt version `research-v0`.
The Ollama adapter has no web or tool bindings. Every forecast, evidence packet, failure
ledger, immutable report, evaluation, model digest, and code commit is persisted.

## Output

By default the run is written to a sibling directory rather than the repository:

```text
../trading-llm-local-runs/
  llama31-development-v0.1-<UTC timestamp>-<commit>/
    model-metadata.json
    blind/
    market-aware/
    local-development-summary.json
```

`local-development-summary.json` is the compact handoff artifact to inspect first. It records
the exact code commit, exact Ollama model digest, frozen input identities, and the blind and
market-aware execution/evaluation summaries.

Do not access the final holdout after seeing this run unless the development methodology has
been explicitly frozen first. Human beings invented p-hacking long before LLMs arrived; the
repository does not need to rediscover it.
