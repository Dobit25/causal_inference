# Phase E — Shared Semantic Execution

**Authorization:** granted in conversation after checkpoint commit `642ad1d1`  
**Result:** `STOPPED_MISSING_HASH_PINNED_SEMANTIC_INPUTS`

## Provider preflight

The authorized worst-case preflight was executed with the frozen production prompt/schema:

- 7 nodes / 21 candidate pairs;
- model `gpt-5.4-nano-2026-03-17`;
- truncation disabled;
- structured output schema v3;
- no study scene, Oracle, or holdout data.

Provider result: **PASS**.

| Item | Result |
|---|---:|
| Input tokens | 896 |
| Output tokens | 713 |
| Total tokens | 1,609 |
| Reasoning tokens | 0 |
| Latency | 8,203 ms |
| Request ID | `req_d6dfa32041034c68af7234ed90d68f1e` |
| Context check | completed without truncation |
| Study semantic calls | 0 |

The provider preflight artifact is `data/manifests/p1v3_phase_e_provider_preflight.json`.

## Why study execution stopped

Phase D materialized observations and statistical graph artifacts, but the repository contains no hash-pinned public story/input manifest for the 30 development scenes. The frozen Phase E checkpoint does not authorize deriving stories from hidden SCM/Oracle state, and the runner therefore refused to manufacture semantic inputs.

Consequently:

- planned study semantic calls: **0**;
- actual study semantic calls: **0**;
- provider attempts for study execution: **0**;
- Oracle access: **0**;
- holdout access: **0**;
- downstream reasoner calls: **0**.

This is a fail-closed execution stop, not a model or context failure. No prompt, schema, model, truncation rule, candidate pool, or closure rule was changed.

The machine-readable stop audit is `data/manifests/p1v3_phase_e_shared_semantic_execution_audit.json`.

## Required next step

Before Phase E can be rerun, create and separately hash-freeze the public semantic-input manifest for exactly `P1V3SD000–P1V3SD029` (including story variant, public story text/hash, pair-pool identity, and graph-input hash). That amendment must preserve the current prompt/schema/model and must not expose Oracle labels to the model. A new explicit execution authorization is required afterward.
