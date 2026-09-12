# T07 Grading-Only Oracle Loader Report

## Verdict

```yaml
t07_complete: true
oracle_loader_ready: true
canonical_graph_schema: fourgraph.graph.v1
development_scenes_valid: 8/8
holdout_accessed: false
downstream_reasoner_used: false
t05_artifacts_changed: false
```

T07 implements the grading-only CausalDS loader that converts a released ground-truth DAG into the same canonical graph artifact used by all four experimental conditions. It also removes grading access from the runtime SCD module and adds enforceable access/leakage tests.

## Data flow

```text
public schema.json ──> VariableMap X000...
                              \
grading ground_truth.json ─────> Oracle-only loader ─> G_ORACLE GraphArtifact
                                                        ├─ audit view
                                                        ├─ metrics view
                                                        └─ provenance-blind reasoner view
```

The loader consumes only public schema metadata and the graph/mapping fields required from `ground_truth.json`. Because the released JSON file also contains grading fields, the parser necessarily reads the file bytes, but those extra fields are never used, returned, or logged. The loader never opens grading test values or graph images.

## Access boundary

`GradingPurpose` is a typed capability with an artifact matrix:

- `ORACLE` may resolve only `ground_truth`;
- `INTEGRITY_AUDIT` retains the T04 audit scope;
- `SCORING` remains reserved for post-inference grading.

Passing a string such as `"oracle"` is rejected. The production SCD module no longer imports the grading resolver or an Oracle helper. The T05 development-scoring compatibility helper now lives in the Oracle module; this changes no frozen T05 output.

## Validation

For every loaded scene, T07 verifies:

- scene ID agreement;
- public schema column count and deterministic order;
- public/ground-truth observed-node bijection;
- no latent nodes in released P0;
- complete named-node mapping;
- known edge endpoints;
- equality of observed/full edges for the no-latent scene;
- no self-loop, duplicate/conflicting adjacency, or directed cycle;
- canonical `oracle/dag/dag` provenance and T06 hashes.

Invalid scene IDs, latent nodes, node mismatches, unknown endpoints, cycles, untyped grading purposes, and out-of-scope Oracle artifacts are covered by negative tests.

## Development integration result

The deterministic audit loaded only the eight T04-frozen graph-development scenes:

- scenes attempted/succeeded: 8/8;
- node-count range: 3–7;
- edge-count range: 2–7;
- valid canonical DAGs: 8/8;
- holdout scenes accessed: 0/25;
- downstream reasoner calls: 0.

The versioned audit stores scene IDs, counts, mapping/input/graph/artifact hashes, and validation status. It deliberately stores no Oracle edge list or raw grading content.

## Reproducibility

```powershell
conda run -n cau python scripts/audit_causalds_t07.py <extracted-causalds-source-root>
conda run -n cau python scripts/audit_causalds_t07.py <extracted-causalds-source-root> --check
```

The `--check` mode regenerates `data/manifests/t07_oracle_loader_audit.json` and requires exact byte equality. It also verifies all four T05 freeze anchors before succeeding.

Final verification in conda environment `cau`: the T07 audit reproduced byte-for-byte; T04 reproduced all integrity/frozen artifacts; T05 reran its selected development graphs and passed; all three relevant configs loaded; and the full repository suite passed (`59 passed`).

## Scope boundary

T07 does not calculate graph metrics, consume task gold-answer fields, run the downstream reasoner, or materialize holdout Oracle graphs. Those actions remain T11, T12, and T14 respectively.
