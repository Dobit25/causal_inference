# Canonical Graph Contract v1

## Purpose

`fourgraph.graph.v1` is the single graph artifact exchanged by `G_LLM`, `G_SCD`, `G_HYBRID`, `G_ORACLE`, the fixed reasoner, and graph metrics. Source-specific code may construct a graph differently, but it must cross this boundary before any comparison or downstream use.

The contract separates three concerns:

1. graph structure: canonical nodes and directed/undirected edges;
2. audit metadata: builder, evidence class, input/config/parent hashes, seed, and edge decisions;
3. consumer views: a provenance-blind reasoner view and a normalized metrics view.

## Canonical node universe

Every scene has a separate `fourgraph.variable_map.v1` artifact. Variables receive contiguous IDs `X000`, `X001`, ... in the public schema order. The order is never inferred from a graph builder's output.

The public mapping is deliberately kept outside graph artifacts:

```json
{
  "scene_id": "scene_000001",
  "variables": [
    {"canonical_id": "X000", "public_name": "Treatment", "variable_type": "binary"},
    {"canonical_id": "X001", "public_name": "Outcome", "variable_type": "continuous"}
  ]
}
```

- SCD receives canonical IDs and declared data types, but not semantic names.
- LLM/Hybrid adapters may receive public names and story semantics.
- The reasoner receives only the non-causal name/type glossary.
- Oracle loading uses the T07 typed grading-only path; it has no raw grading-document return and runtime SCD has no dependency on it.

This prevents column order, display names, or builder-specific labels from silently creating different node universes.

## Graph artifact

A graph artifact contains:

| Field | Meaning |
|---|---|
| `schema_version` | Always `fourgraph.graph.v1` |
| `scene_id` | Scene/SCM owning this graph |
| `graph_method` | `llm`, `scd`, `hybrid`, or `oracle` |
| `graph_type` | Mathematical object: `dag` or `cpdag` |
| `graph_view` | Experimental role: `dag`, `cpdag`, or `projected_dag` |
| `nodes`, `edges` | Canonical graph structure |
| `provenance` | Builder and evidence audit; never sent to the reasoner |
| `edge_audit` | Ordered edge-level decisions, especially projection/hybrid orientations |
| `graph_sha256` | Hash of normalized structure only |
| `artifact_sha256` | Hash of structure plus provenance/audit |

An edge is either:

```json
{"source":"X000","target":"X001","mark":"directed"}
```

meaning `X000 -> X001`, or:

```json
{"source":"X000","target":"X001","mark":"undirected"}
```

meaning that the adjacency is present but its direction is unresolved. Undirected endpoints are stored lexicographically; nodes and edges are always sorted.

### Method/view matrix

| Method | Accepted primary view | Other accepted view |
|---|---|---|
| LLM | DAG | none |
| SCD P0 | CPDAG | deterministic projected DAG sensitivity |
| SCD P1 | DAG | none initially |
| Hybrid H1 | DAG | none |
| Oracle | DAG | none |

`graph_type` and `graph_view` are not interchangeable. A projected graph is mathematically a DAG, but its experimental role remains `projected_dag` so it cannot be mistaken for direction learned from observations.

## Validation

The Python semantic validator is authoritative. JSON Schema checks record shape; it cannot alone express graph theory, evidence isolation, or parent-child relations.

Every artifact is checked for:

- exactly one contiguous canonical node universe, currently 1–8 nodes;
- known marks, methods, types, and views;
- no self-loop, duplicate, conflicting adjacency, or directed cycle;
- method-specific evidence allowlists and required config/input hashes;
- DAGs containing only directed edges;
- CPDAGs having a consistent extension and equalling the exact completed PDAG of that extension.

Exact CPDAG validation enumerates Markov-equivalent topological orders. The 8-node bound covers the released P0 range of 3–7 nodes and the planned P1 range of 5–7 nodes.

### Projection relationship

`validate_projection_relationship(parent, child)` additionally proves that:

- the parent is a raw SCD CPDAG and its artifact hash matches;
- scene, nodes, skeleton, and compelled directions are preserved;
- the child is the frozen lexicographic consistent extension;
- every unresolved edge is oriented and logged exactly once as arbitrary;
- no new incompatible unshielded collider or cycle appears.

### Hybrid H1 relationship

`validate_hybrid_relationship(parent, child)` proves the same parent, node, skeleton, compelled-direction, and equivalence-class constraints. Every unresolved edge must be logged exactly once as a non-arbitrary semantic decision. H1 therefore cannot add, delete, or repair adjacencies.

## Serialization and hashes

Canonical JSON uses UTF-8, lexicographically sorted keys, compact separators, finite numbers only, and one final LF for file/JSONL records. SHA-256 digests are uppercase hexadecimal.

File loaders reject semantically equivalent JSON whose exact bytes are not canonical. `.gitattributes` forces LF for versioned configs, schemas, and manifests so checkout behavior on Windows cannot silently invalidate their hashes.

- `mapping_sha256` identifies a scene's canonical/public variable mapping.
- `graph_sha256` covers `fourgraph.structure.v1` plus canonical nodes and edges only. Identical structures from different methods intentionally share this hash.
- `artifact_sha256` covers the full graph artifact except the self-referential `artifact_sha256` field. It changes when provenance or edge audit changes.
- Manifest file hashes cover exact bytes and detect newline or serialization drift.

The two graph hashes answer different questions: “are these structures the same?” and “are these complete audited artifacts the same?”

## Consumer isolation

`GraphArtifact.reasoner_view()` returns only:

```json
{"schema_version":"fourgraph.reasoner_graph.v1","graph_type":"dag|cpdag","nodes":[],"edges":[]}
```

It excludes scene ID, method/view labels, builder, evidence sources, parent/input/config hashes, and edge audit. The reasoner therefore cannot infer whether a structure came from LLM, SCD, Hybrid, or Oracle.

`GraphArtifact.metrics_view()` returns the normalized `PartialGraph` structure. Audit/reporting retains the complete artifact.

## Versioned implementation and reproducibility

- Frozen policy: `configs/graph_contract_v1.yaml`
- Record schemas: `schemas/graph_contract_v1.schema.json`, `schemas/variable_map_v1.schema.json`, and `schemas/reasoner_graph_v1.schema.json`
- Semantic implementation: `src/fourgraph/graph_contract.py`
- Source adapters: `src/fourgraph/graph_adapters.py`
- Synthetic cross-method fixture: `data/manifests/t06_graph_contract_examples.jsonl`
- T06 manifest: `data/manifests/graph_contract_v1.json`

Regenerate or verify all T06 derived artifacts without benchmark or holdout access:

```powershell
conda run -n cau python scripts/build_graph_contract_t06.py
conda run -n cau python scripts/build_graph_contract_t06.py --check
```

The T05 files remain byte-identical. T06 tests prove that the eight selected T05 CPDAG records can be wrapped by v1 adapters, while future graph builders will emit v1 artifacts directly.
