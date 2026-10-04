# Calibration public-story generation amendment

Status: `PASS_CALIBRATION_PUBLIC_STORIES_FROZEN`

The amendment replays the frozen T19 generator on the first 120 calibration
identities only. It does not change the prompt, response schema, model,
thresholds, or scene split.

## Frozen generation

- Cohort: exact `role=semantic_calibration` prefix of 120 identities in frozen
  plan order; namespace `P1V3SC`.
- Generator: `src/fourgraph/p1_stories.py`, hash-pinned to the T19
  implementation.
- Story config: `configs/t19_p1_semantic_stories.yaml`, hash-pinned.
- Master seed and alias rules: unchanged T19 values (`1701`, seeded neutral
  aliases independent of graph structure).
- Variants: 120 Full, 120 Partial and 120 Ambiguous public stories.
- Non-edge is not a fourth story variant; it is a frozen pair diagnostic over
  an allowed public story input.
- The public model view contains only `builder_input.story`.

## Results

- Scenes materialized: `120/120`.
- Public stories: `360/360`.
- Variant counts: Full `120`, Partial `120`, Ambiguous `120`.
- Story generator validation: PASS for every scene/variant.
- Replay: byte-for-byte PASS.
- Leakage audit: PASS; no canonical IDs, Oracle/CPDAG metadata, gold labels or
  holdout information in public story inputs.
- Semantic API calls: `0`.
- Oracle scoring: `0`.
- Holdout access: `0`.

Artifacts are listed in
`data/manifests/p1_v3_nano_medium_calibration_public_story_generation_audit.json`.
The public story manifest hash is recorded in that audit.

## Remaining live gate

This amendment authorizes only offline story/data generation. It does not
authorize semantic API calls. Before live execution, the runner must consume
the public-story mapping above (the Non-edge diagnostic uses a registered
public story plus its frozen pair subset) and a separate live-authorization
checkpoint must pin the generated artifacts and provider preflight.
