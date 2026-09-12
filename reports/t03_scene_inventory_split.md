# T03 — CausalDS Scene Inventory and Provisional Nested Split

## Status and boundary

```yaml
task: T03
status: complete
split_status: provisional_until_t04_integrity
exact_ids_frozen: false
```

Historical note: T04 subsequently passed all 33 scenes and froze this allocation unchanged in `data/manifests/p0_frozen_split.json`. This report preserves the pre-T04 status of the T03 artifact.

T03 inventories metadata for all 100 released scenes and produces a reproducible nested allocation. It reads `tasks.json`, `schema.json`, file presence, and grading-only graph/mechanism metadata. It does not inspect parquet values, missingness, empirical dtypes, or row-level mappings; those checks belong to T04.

## Complete inventory

The canonical inventory is `data/manifests/causalds_scene_inventory.jsonl`: one deterministic JSON record per scene, sorted by `scene_id`.

| Property | Result |
|---|---:|
| Scenes | 100 |
| Rows declared by schema | 16,000 for every scene |
| Observation variants | 48 clean, 32 proxy, 20 proxy-hard |
| Graph nodes | 3–8 |
| Graph edges | 2–8 |
| Valid released DAG metadata | 100/100 |
| Complete node mapping metadata | 100/100 |
| Complete per-node mechanism metadata | 100/100 |
| Task count per scene | 11–44 |
| Unique released task IDs | 90 |
| Conceptual data family | 84 mixed binary/continuous, 16 continuous-only |

The inventory records task IDs/types/rungs, public schema dtypes and binary flags, graph size/density, observed/latent counts, mapping checks, motif/structural label, conceptual variable types, SCM profiles, mechanism/noise counts, and neural/heteroscedastic/discretized flags. These are released metadata summaries, not reconstructed structural equations.

Mechanism heterogeneity is material: the release contains eight continuous SCM profiles and seven binary profiles. Eleven scenes report neural nodes, seven report heteroscedastic nodes, and none report discretized nodes. This supports inventory and stratification but does not select a valid P0 SCD algorithm; that decision remains T05 after T04.

## Eligibility reproduction

The deterministic rules reproduce:

| Cohort | Scenes | Role |
|---|---:|---|
| Graph | 33 | Graph construction and structural evaluation |
| Primary downstream | 27 | Same five frozen tasks per scene |
| Supplementary | 6 | Exploratory only; never pooled with primary accuracy |

Primary and supplementary are disjoint and their union equals the graph cohort.

## Stratification

Algorithm: `deterministic_nested_balance_v1`, seed 42, 64 SHA-256-seeded starts followed by deterministic swap improvement and lexicographic tie-breaking.

Numeric balance features:

- graph node count;
- edge density relative to the maximum DAG edge count;
- binary conceptual-node fraction;
- neural/heteroscedastic/discretized-node fraction.

Categorical balance features:

- graph-size band;
- density band;
- continuous-only versus mixed data family;
- structural motif/label.

Before minimizing centroid loss, graph and primary development subsets must cover every categorical stratum appearing at least three times in their cohort. Detailed high-cardinality SCM profiles are inventoried but not treated as exact strata because doing so would create many singleton cells and make a 7/20 split unstable.

## Provisional allocation

### Graph cohort — 8 development / 25 holdout

Development:

```text
scene_000098  scene_000172  scene_000402  scene_000415
scene_000511  scene_000719  scene_000792  scene_000814
```

Holdout is the remaining 25 graph scenes recorded in `data/manifests/p0_provisional_split.json`.

### Primary downstream — 7 development / 20 holdout

Development:

```text
scene_000098  scene_000172  scene_000415  scene_000511
scene_000719  scene_000792  scene_000814
```

Holdout:

```text
scene_000215  scene_000224  scene_000253  scene_000255
scene_000281  scene_000372  scene_000395  scene_000399
scene_000425  scene_000499  scene_000594  scene_000665
scene_000757  scene_000778  scene_000822  scene_000836
scene_000864  scene_000907  scene_000976  scene_000977
```

### Supplementary — 1 development / 5 holdout

Development: `scene_000402`.

Holdout: `scene_000338`, `scene_000521`, `scene_000628`, `scene_000699`, and `scene_000966`.

The graph development set is exactly primary development plus supplementary development. The same identity holds for holdout, so no scene changes role between cohort views.

## Balance result

The selected objective loss is `0.32865675`, compared with a median initial-candidate loss of `2.68333173`.

| Cohort | Maximum absolute standardized mean difference across numeric features |
|---|---:|
| Graph | 0.079 |
| Primary downstream | 0.029 |
| Supplementary | 0.537 |

Graph development covers all three size bands, all three density bands, both data families, and every structural label occurring at least three times. Primary development does the same for its common strata. Supplementary has only one development scene, so it cannot cover its fork/collider/grafted motifs or both size bands; this is an explicit design limitation and why supplementary downstream results remain exploratory.

## Reproducibility artifacts

- Generator: `scripts/build_causalds_t03.py`.
- Inventory: `data/manifests/causalds_scene_inventory.jsonl`.
- Split: `data/manifests/p0_provisional_split.json`.
- Inventory SHA-256: `24B27919AAA0E8828C2F635627856D35FA3D3785A1C1933B59E1A18C8D739562`.
- Split SHA-256: `4D6FAB447F955954BF421D2A2EE6CE3396D470A01DF086AE4553AE6ED3498508`.

## T03 Definition of Done

- [x] All 100 scenes inventoried.
- [x] Graph/task/type/latent/row/mechanism metadata recorded.
- [x] Nested 33/27/6 eligibility reproduced.
- [x] Deterministic stratification criteria declared.
- [x] Provisional 8/25, 7/20, and 1/5 allocation generated.
- [x] Partition, nesting, single-role, coverage, and balance checks pass.
- [x] Generator can reproduce and byte-check both artifacts.
- [x] Split remains explicitly provisional.
- [ ] Parquet-level integrity and final freeze — T04.
