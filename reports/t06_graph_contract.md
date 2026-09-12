# T06 Canonical Graph Contract Report

## Verdict

```yaml
t06_complete: true
canonical_graph_contract_ready: true
schema_version: fourgraph.graph.v1
holdout_accessed: false
t05_method_selection_reopened: false
```

T06 converted the minimal T05 `PartialGraph` representation into one versioned, validated, hash-stable artifact for LLM, SCD, Hybrid, Oracle, reasoner, and graph metrics.

## Work completed

1. Froze deterministic scene-level variable IDs `X000...` and a separately hashed public variable map.
2. Defined directed/undirected edge semantics, method/type/view combinations, canonical ordering, UTF-8 JSON serialization, and separate structure/artifact hashes.
3. Added source-specific factories that all emit `GraphArtifact` and enforce evidence allowlists.
4. Added DAG acyclicity and exact completed-PDAG validation for the project graph-size range.
5. Added deterministic consistent-extension traces and cross-artifact validation for projected DAGs.
6. Added H1 parent validation: same scene/nodes/skeleton, preserved compelled directions/equivalence class, and exactly one semantic audit record per unresolved edge.
7. Added provenance-blind reasoner and normalized metrics views.
8. Generated a synthetic five-artifact fixture covering LLM DAG, raw SCD CPDAG, projected SCD DAG, Hybrid DAG, and Oracle DAG. No CausalDS development or holdout values were read.

## Reproducibility evidence

`scripts/build_graph_contract_t06.py --check` regenerates and compares these artifacts byte-for-byte:

- `data/manifests/t06_variable_map_example.json`;
- `data/manifests/t06_graph_contract_examples.jsonl`;
- `data/manifests/graph_contract_v1.json`.

The manifest records hashes for the frozen contract config, all three JSON Schemas, generated fixtures, and four T05 freeze anchors. The generator aborts if a T05 anchor changes.

## Compatibility and boundary checks

- All four graph sources use one node/edge artifact class.
- Identical projected and Hybrid fixture structures share `graph_sha256` but have different `artifact_sha256` values because their provenance differs.
- Their reasoner views are byte-equivalent, proving method provenance is stripped.
- All eight T05-selected development CPDAG records validate under the v1 adapter without rewriting T05 outputs.
- T06 did not open the 25 graph-holdout scenes or run a downstream reasoner.

Final verification in conda environment `cau`: both experiment configs loaded, the T06 generator reproduced all three outputs byte-for-byte, the CLI validated the variable map, and the full test suite passed (`46 passed`).

## Remaining scope

The contract does not itself call an LLM, run BOSS/DirectLiNGAM, calculate final graph metrics, or solve CPDAG queries. T07 now supplies the grading-only Oracle loader; T08–T12 remain downstream consumers of the T06 boundary.
