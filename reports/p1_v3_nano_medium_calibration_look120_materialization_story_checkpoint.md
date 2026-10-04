# Look-120 materialization and public-story checkpoint

Status: `BLOCKED_CALIBRATION_STORY_PROTOCOL`

This checkpoint verifies the exact 120-scene calibration prefix before any
study write or semantic live execution. The frozen identity plan selects 120
`role=semantic_calibration` records in plan order, all in the `P1V3SC`
namespace. Development (`P1V3SD`) and validation (`P1V3SV`) identities are
rejected.

## Why the checkpoint is blocked

The repository contains the T19 public-story protocol and artifacts only for
the 30-scene method-development cohort (`P1V3SD000–029`). That protocol is
explicitly scoped to method development. No calibration story-generation
amendment or public story artifacts for the 120 `P1V3SC` scenes are currently
frozen.

The checkpoint therefore does not:

- relabel or copy development stories;
- infer stories from Oracle/SCM data without a registered calibration story
  protocol;
- rewrite stories with an LLM;
- materialize scenes before the story contract is resolved;
- consume the existing live authorization or call the semantic API.

## Audit result

- Exact calibration identities: 120/120 verified.
- Namespace/role guard: PASS.
- Runner/materializer/execution-plan hashes: PASS.
- Calibration scene artifacts: absent.
- Calibration public story artifacts: absent.
- Scene writes: 0.
- BOSS fits: 0.
- Bootstrap-BOSS fits: 0.
- Semantic API calls: 0.
- Oracle/validation/holdout access: 0.
- Live execution enabled: false.

The exact audit is stored at
`data/manifests/p1_v3_nano_medium_calibration_look120_materialization_story_checkpoint_audit.json`.

## Required next amendment

Freeze a calibration-specific public-story generation amendment that records
the T19 generator/version, allowed source inputs, alias/seed policy, exact
120 IDs, registered variants (Full/Partial plus the registered diagnostic
handling), output schema, and leakage audit. After that amendment passes,
materialize the 120 scenes, generate/verify the public stories, rerun this
checkpoint, and only then request a separate live-execution authorization.
