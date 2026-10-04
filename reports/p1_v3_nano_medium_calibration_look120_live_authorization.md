# Nano-medium calibration look 120 — authorization update

## Status

The user explicitly authorized the first calibration look, scoped to exactly
120 registered semantic-calibration scenes. The authorization is recorded, but
execution is **blocked fail-closed before any study call** because the current
runner is still offline plumbing: its provider adapter and successor-scene
materialization adapter are disabled/not ready.

## What was not done

- No calibration SCM or observational data was materialized.
- No Single/Bootstrap-BOSS or other statistical fit ran.
- No semantic API call ran.
- No Oracle, validation or holdout data was accessed.
- No metric or confidence-sequence scoring started.

## Why execution stopped

The frozen control runner only supports read-only `--dry-run`, `--check` and
ledger `--resume` modes. It deliberately does not implement the production
chain `identity plan → SCM/data materialization → statistical parent → public
story/input → six semantic calls → token ledger`. Calling the provider now
would violate the registered execution boundary.

## Next step

Build and separately freeze the production look-120 runner and its adapters,
including exact-prefix materialization, Single/Bootstrap-BOSS execution,
semantic cache/idempotency and per-call provider-usage commits. Then run an
offline fixture/dry-run audit. Only after that audit may the recorded
authorization be consumed for live look 120.
