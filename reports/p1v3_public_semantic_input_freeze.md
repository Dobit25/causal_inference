# P1V3 public semantic-input freeze

**Status: FAIL — missing registered public artifacts**

This checkpoint searched only already registered public story/input registries. It did not generate stories, inspect SCM/Oracle graphs, read holdout data, or call an API.

The exact required IDs are `P1V3SD000–P1V3SD029`. The repository contains observations and statistical metadata for these IDs, but no registered public story/input artifact for them. Existing T19 story artifacts use the different `P1S...` cohort and therefore cannot be relabeled or reused.

Result: **0/30 semantic inputs identified**. The freeze gate is not met. Hash, mapping, leakage, and replay PASS cannot be claimed for absent inputs.

Artifacts:

- `configs/p1v3_public_semantic_input_manifest.yaml`
- `data/manifests/p1v3_public_semantic_input_audit.json`

The next valid step is a separately authorized public-story/input generation-and-freeze amendment for exactly these 30 scenes. Until it passes, do not request Phase E semantic execution authorization.
