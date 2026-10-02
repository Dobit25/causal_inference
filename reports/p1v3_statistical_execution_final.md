# Phase D — Final statistical execution report

## Verdict

**PASS — Phase D complete; Phase E remains locked.**

Execution used the separately authorized overlay
`configs/p1v3_statistical_execution_live_authorized.yaml`. Frozen protocol and
algorithm manifests were not modified. All fits ran with concurrency `1`.

## Counts

| Condition | Planned | Final normalized fits |
|---|---:|---:|
| Single-BOSS | 30 | 30 |
| Bootstrap-BOSS | 6,000 | 6,000 |
| PC | 30 | 30 |
| MMPC | 30 | 30 |
| FGES | 30 | 30 |
| GFCI | 30 | 30 |
| **Total** | **6,150** | **6,150** |

- Raw artifacts: `6,150/6,150`.
- Normalized artifacts: `6,150/6,150`.
- Missing/incomplete artifact pairs: `0`.
- Unknown execution identities: `0`.
- Final failed jobs: `0`.
- Configured retry count: `0`.
- Historical error artifacts: `60`; all are preserved as incident evidence and
  all 60 are marked superseded by a successful resume artifact. They are not
  counted as final failed jobs.

## Audit checks

- Config/dependency hash consistency: PASS (`0` failures).
- Graph schema and validity: PASS (`0` failures).
- Execution identities: PASS; no duplicate scientific identity.
- Materialized study scenes: exactly `30` development scenes.
- Oracle access: `0`.
- Holdout access: `0`.
- Semantic API calls: `0`.
- Phase E execution: `0`.

The initial run exposed 30 GFCI constructor errors and 30 MMPC Windows/R
subprocess errors. These were recorded, the adapter-level fixes were committed,
and `--resume` reran only the missing identities. No successful fit was rerun.
The normalized metadata was then enriched offline from the already-recorded raw
job identity; no fit was rerun during that repair.

## Artifacts

- Plan: `data/manifests/p1v3_statistical_execution_plan.json`
- Final audit: `data/manifests/p1v3_statistical_execution_audit.json`
- Raw fits: `results/p1v3_statistical_ensemble/raw/`
- Normalized fits: `results/p1v3_statistical_ensemble/normalized/`
- Error/incident records: `results/p1v3_statistical_ensemble/errors/`

## Next authorized step

Do not start Phase E automatically. The next step is a separate
`PHASE_E_SHARED_SEMANTIC_EXECUTION_AUTHORIZATION_CHECKPOINT`. That checkpoint
must verify the Phase D audit hash and authorize the frozen shared semantic pool
before any provider call is made.
