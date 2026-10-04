# P1 v3 Nano-medium look-120 production runner freeze

Status: `PASS_OFFLINE_PREFLIGHT_LIVE_BLOCKED`

This checkpoint freezes execution plumbing for the registered first
calibration look. It does not materialize study scenes, execute BOSS, or call
the semantic provider.

## Frozen scope

- Cohort: exactly the first 120 `role=semantic_calibration` identities from
  the frozen exact identity plan, in frozen plan order.
- Statistical parent: 120 Single-BOSS fits and 24,000 Bootstrap-BOSS fits
  (200 repetitions per scene; 2,000 rows sampled with replacement).
- Semantic certification: Full and Partial, six registered prompt variants
  per story and scene.
- Diagnostics: the registered 120-scene Ambiguous subset and 80-scene
  Non-edge subset, six prompt variants each.
- Model: `gpt-5.4-nano-2026-03-17`, `reasoning_effort=medium`; prompt, schema,
  output limit, structured-output setting and truncation policy are hash-pinned
  to the existing checkpoint.
- Concurrency: 1. Token accounting uses the existing provider-reported
  3,000,000-token hard stop and Asia/Ho_Chi_Minh 07:00 reset policy.

## Planned workload

| Component | Planned |
|---|---:|
| Calibration scenes | 120 |
| Single-BOSS fits | 120 |
| Bootstrap-BOSS fits | 24,000 |
| Semantic calls | 2,640 |
| Maximum transport attempts | 2,904 |

The 2,640 semantic calls are `120 x 2 x 6` certification calls, plus
`120 x 6` Ambiguous diagnostics and `80 x 6` Non-edge diagnostics.

## Controls

The runner derives one deterministic execution identity for every statistical
fit and one idempotency identity for every semantic request. Duplicate keys
fail closed; resume can only consume an existing matching cache entry. The
runner records paths for raw responses, cache entries, request metadata and
the append-only token ledger. No automatic next look, validation, Oracle or
holdout access is enabled.

## Offline verification

- Frozen parent hashes verified: PASS.
- Exact 120-scene selector and registered prefix: PASS.
- Statistical job count: `24,120`: PASS.
- Semantic job count: `2,640`: PASS.
- Statistical identity replay: PASS.
- Semantic identity replay: PASS.
- Materialization adapter check: `120` planned, `0` writes.
- Provider calls: `0`.
- Statistical fits: `0`.
- Scenes materialized: `0`.
- Oracle/validation/holdout access: `0`.

The generated preflight audit is
`data/manifests/p1_v3_nano_medium_calibration_look120_preflight_audit.json`;
the deterministic plan is
`data/manifests/p1_v3_nano_medium_calibration_look120_execution_plan.json`.

## Deliberate stop

The freeze leaves live execution disabled. The two expected input roots are
not materialized yet:

```text
data/generated/p1_v3_nano_medium_calibration_look120
data/generated/p1_v3_nano_medium_calibration_look120_stories
```

Therefore the existing user authorization is not consumed by this offline
checkpoint. A separate live checkpoint must first verify materialized scenes,
public stories, provider preflight, and the unchanged hash bundle; only then
may the runner be switched to live execution.
