# Prospective live-capture pilot v0.1 operational clarification

Status: frozen before the first live market-universe query for this pilot.

This clarification resolves execution details left unspecified in the v0.1 preregistration. It does not change the pilot's scientific question, market-selection rule, evidence source, comparator, model identity, residual mapping, outcome blindness, or success threshold.

## Selection-to-acquisition timing

The structural selection stage freezes all eight selected candidate identities before evidence capture begins.

Every selected row's evidence capture must begin no later than **120 minutes after `selection_snapshot_at`**.

If a selected row cannot begin acquisition inside this window, that row is an operational failure and is not replaced.

The 120-minute bound is an execution envelope only. Selection remains blind to evidence availability and later market movement.

## Acquisition before inference

For all eight selected rows, time-sensitive acquisition is completed and frozen before any model inference begins.

For each row the acquisition sequence remains:

1. capture/freeze Google News RSS evidence;
2. if evidence is terminal (`verified_complete` or `verified_empty`), acquire/freeze CLOB bid, ask, and midpoint;
3. verify CLOB validity;
4. verify midpoint timestamp is not earlier than evidence completion and is no later than 15 minutes after evidence capture start;
5. freeze the bound acquisition record.

Only after acquisition has been attempted for all eight rows may the local Llama forecaster run on rows with terminal evidence and a valid bound market snapshot.

This two-phase design prevents model runtime from consuming the selection-to-acquisition window for later rows.

## Local Ollama model verification

Before the first model request, the worker must query the local Ollama model registry and verify that tag `llama3.1:8b` resolves to the frozen digest:

`sha256:46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`

A missing model, registry failure, or digest mismatch forbids model inference. It is an operational failure, not permission to use another model.

## Model request timeout

The local Ollama request timeout is frozen at **1200 seconds per model request**.

This timeout changes only the local execution envelope. The model tag, digest, temperature, seed, prompt family, one-request rule, residual mapping, and model-failure no-op behavior remain unchanged.

## Acquisition and inference artifacts

A row's acquisition record is immutable once frozen. Model inference may read the frozen row artifact but may not update its evidence or market snapshot.

Raw RSS, raw CLOB responses, parsed evidence, bound EvidencePacket, forecast record, and session summaries must be written to local persistent storage with SHA-256 hashes.

No outcome or post-forecast market lookup is permitted during either phase.
