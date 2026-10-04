# Nano-medium sequential calibration authorization checkpoint

## Purpose

This checkpoint requests permission for a separate Nano-medium semantic
calibration phase. It is not a live authorization by itself. The primary model
is `gpt-5.4-nano-2026-03-17` at medium reasoning effort; Mini-medium remains a
historical comparator and no multi-model matrix is opened.

## Frozen execution scope

The phase uses the exact 440 scenes registered as
`role=semantic_calibration` in the frozen identity manifest. Only the prefixes
at looks 120, 160, 200, 240, 280, 320, 360, 400 and 440 may be inspected. Full
and Partial are certification variants. Ambiguous (120 scenes) and non-edge (80
scenes) are diagnostic subsets. Validation, development re-runs and holdout
access are forbidden.

The statistical parent is the frozen Ensemble 3/5 (Single-BOSS,
Bootstrap-BOSS, PC, MMPC, FGES); C1–C6 remain sensitivity conditions. Prompt,
schema, six-vote agreement, pair-level abstention and condition-specific
closure are hash-pinned and cannot be changed after authorization.

## Budget and safeguards

The maximum is 6,480 logical calls and 7,128 attempts with the registered
transport reserve. Using the frozen Phase-E Nano usage and the official Nano
rate card, the point estimate is USD 9.9378846; with a 25% reserve it is USD
12.42235575. Each registered look has its own cumulative cost stop. A fresh
platform spend/limit attestation and an exact-contract provider preflight are
required immediately before live execution. The existing provider preflight
cannot be silently reused if its prompt/schema hashes differ.

## Gate

Calibration must establish scene-level confidence-sequence evidence for both
Full and Partial automatic policies, with precision lower confidence bound at
least 0.95, scene-mean coverage at least 0.20, graph validity 1.00, the High
guardrail at 0.90, and the registered Ambiguous abstention ceiling. Failure
means stopping before validation; no threshold lowering or prompt tuning is
permitted.

## Current status

The checkpoint is ready for review but **not authorized**. At creation time:
scenes materialized = 0, statistical fits = 0, semantic API calls = 0,
Oracle/validation/holdout access = 0.
