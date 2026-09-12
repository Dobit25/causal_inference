# T09 Development SCD Graph Builder Report

## Verdict

```yaml
t09_complete: true
scd_graph_builder_ready: true
development_raw_cpdag: 8/8
development_projected_dag: 8/8
holdout_accessed: false
story_or_semantics_accessed: false
oracle_accessed: false
deterministic_replay: true
blocker: null
```

T09 materialized the T05-frozen statistical discovery method as canonical T06 graph artifacts. It did not reopen method selection or use T05 oracle metrics as builder evidence. The builder reran `BOSS + BasisFunctionBicScore` directly from each scene's clean public observational table and public schema types.

## Frozen method and runtime

- selected candidate: `boss_basis_bic__p1__t3`;
- penalty discount: `1.0`;
- basis truncation: `3`;
- one deterministic data-order start, no BES;
- output: raw CPDAG;
- backend: direct JPype call to Tetrad `7.6.11-SNAPSHOT` JAR with SHA-256 `5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051`;
- runtime: Python 3.10.21, Java 21.0.10, JPype 1.6.0, NumPy 1.26.4, PyArrow 23.0.1.

The historical T05 selection config records Python 3.10.20. T09 does not rewrite it: the production config records the actual patched Python 3.10.21 environment, and the independent T05 selected-method regression still passes with exactly matching graphs.

## Evidence boundary

The builder uses only `clean/data.parquet` and the type/mapping information required from `clean/schema.json`. Column names are replaced by contiguous `X000...` identifiers before discovery. Binary variables remain exact two-category variables; continuous variables receive per-scene sample z-scoring. The 16,000 rows of each scene remain separate.

The T09 code has no dependency on story loading, tasks, LLM graphs, grading access, Oracle graphs, or answers. The frozen scope is exactly the eight graph-development scene IDs; 0/25 holdout scenes were accessed.

## Canonical outputs

For each scene T09 emits:

1. a primary `scd/cpdag/cpdag` artifact with observational/schema input hashes and a complete SCD edge audit;
2. a sensitivity-only `scd/dag/projected_dag` artifact produced by the frozen lexicographic Dor--Tarsi consistent extension.

Every projected DAG references its exact raw CPDAG parent artifact hash, preserves its skeleton and compelled directions, introduces no incompatible collider or cycle, and audits every arbitrary orientation exactly once.

Across the eight scenes, the raw graphs contain 31 adjacencies: 4 directed and 27 undirected. Thus 27/31 adjacencies are unresolved when pooled across scenes (87.1%); T05's reported 90% is the macro scene-average and is therefore not a conflicting value. The result reinforces that raw CPDAG reasoning must remain primary and projected DAGs must remain sensitivity-only.

## Reproducibility

The one-scene gate ran `scene_000098` twice and obtained byte-identical raw and projected artifacts. The full write generated 8 CPDAGs and 8 projections; a separate full rerun with `--check` reproduced all three versioned outputs byte-for-byte. Runtime measurements are machine-specific and stay in ignored `results/raw/t09_scd/runtime.jsonl`.

```powershell
conda run -n cau python scripts/build_causalds_t09.py <extracted-causalds-source-root>
conda run -n cau python scripts/build_causalds_t09.py <extracted-causalds-source-root> --check
```

T09 establishes graph-builder readiness only. Oracle-based graph metrics belong to T11, Hybrid semantic orientation to T10, downstream reasoning to T12, and holdout graph construction to T14.
