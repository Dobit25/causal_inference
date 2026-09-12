# T04 — CausalDS P0 Data Integrity and Final Cohort Freeze

## Verdict

```yaml
integrity_ready: true
graph_scenes_passed: 33/33
primary_task_records: 135
supplementary_task_records: 89
split_status: frozen_after_t04_integrity
```

All 33 graph-cohort scenes passed the registered parquet, schema, mapping, graph, task, and public/grading-boundary gates. No scene was excluded, replaced, or moved between development and holdout. The T03 allocation is therefore frozen unchanged.

## Audit boundary

T04 reads public `data.parquet` and `test_features.parquet` values with PyArrow 23.0.1. It reads grading-only `ground_truth.json` through the explicit `integrity_audit` access purpose to validate DAG, observed/latent status, conceptual mappings, variable types, and public task references.

The grading `test.parquet` is checked for presence and hashed but its values are not read. No gold answer or grading payload is written to either task manifest. T04 does not select or tune an SCD method.

## Public parquet result

### Observational `data.parquet`

| Quantity | Result |
|---|---:|
| Scenes read | 33 |
| Rows | 528,000 = 33 × 16,000 |
| Columns | 120 |
| Actual physical dtype | 120 `float64` |
| Schema-declared binary columns | 34 |
| Null values | 0 |
| NaN values | 0 |
| Infinite values | 0 |
| Constant columns | 0 |
| Binary-support mismatches | 0 |
| Duplicate rows | 0 in every scene |

Every parquet row count, column count, column order, column name, and physical dtype matches `schema.json`. Binary columns use the declared `{0, 1}` support. A physical `float64` column remains conceptually binary when both mechanism metadata and schema binary flags identify it as binary.

### Public `test_features.parquet`

| Quantity | Result |
|---|---:|
| Rows | 132,000 = 33 × 4,000 |
| Columns | 87 |
| Null/NaN/Inf values | 0 |
| Constant columns | 0 |
| Duplicate rows | 0 in every scene |

These files are audited for release consistency only. They are not pooled with observational training rows for SCD.

## Mapping and graph integrity

All 33 scenes satisfy:

- graph metadata is a valid DAG;
- edge list contains no duplicates or self-loops;
- graph-node mapping covers every node exactly once;
- observed conceptual names equal the `data.parquet` column set;
- observed nodes cover the complete graph;
- latent-node count is zero;
- conceptual binary/continuous types agree with schema binary flags;
- per-node mechanism metadata covers every graph node.

## Task integrity

The primary manifest contains exactly `27 × 5 = 135` records. Each primary scene contains one and only one copy of:

1. `identification__one_valid_adjustment_set`;
2. `identification__all_minimal_adjustment_sets`;
3. `identification__minimal_adjustment_set_size`;
4. `identification__n_valid_adjustment_sets`;
5. `bias_diagnostic__forbidden_controls_list`.

All primary response schemas are present, task variable references resolve to public conceptual columns, and public prompts contain the correct treatment/outcome query names.

The supplementary manifest contains all 89 released tasks across six scenes:

| Scene | Tasks |
|---|---:|
| `scene_000338` | 15 |
| `scene_000402` | 12 |
| `scene_000521` | 12 |
| `scene_000628` | 23 |
| `scene_000699` | 16 |
| `scene_000966` | 11 |

Supplementary records are marked `exploratory_only` and must never be pooled into primary accuracy.

Both task manifests contain public identifiers, task metadata, variable references, and prompt/response-schema hashes. They contain no prompt text, graph edges, gold answer, grading record, or ground-truth payload.

## Access isolation

`src/fourgraph/causalds_access.py` provides separate public and grading allowlists:

- public view resolves story, data, schema, tasks, and public test features;
- grading view requires one of `integrity_audit`, `oracle`, or `scoring`;
- public resolution rejects `ground_truth`, grading test data, and graph images;
- grading resolution rejects non-allowlisted purposes.

The audit itself records `grading_parquets_read: []`. Automated tests exercise these rejection paths and scan public/task manifests for forbidden grading keys.

## Frozen nested split

The exact T03 split is preserved:

```text
Graph: 33, dev 8 / holdout 25
├─ Primary downstream: 27 × 5, dev 7 / holdout 20
└─ Supplementary: 6 exploratory, dev 1 / holdout 5
```

Graph development IDs:

```text
scene_000098  scene_000172  scene_000402  scene_000415
scene_000511  scene_000719  scene_000792  scene_000814
```

Primary development excludes supplementary `scene_000402`; all remaining graph IDs retain their T03 holdout role. Any future membership, role, or task-panel change requires a new experiment version and audit trail.

## Versioned artifacts

| Artifact | Records/bytes | SHA-256 |
|---|---:|---|
| `p0_data_integrity.json` | 343,064 bytes | `8156AB5F8199488EBB7C48902E787FB5483ACF9143FEAEEA9086B3616B423523` |
| `p0_primary_task_manifest.jsonl` | 135 / 81,801 bytes | `7E16EFF8853ED8A434C5F184D6649710B8E1DDCFAF05B367726386CBB7D016A9` |
| `p0_supplementary_task_manifest.jsonl` | 89 / 49,588 bytes | `1560942AF77DFB79A19F1CA56EE2994A7403844C4E959E2CF061B8EB2084D83B` |
| `p0_frozen_split.json` | 18,277 bytes | `9246C8C73D1AD7204E8E8081D2E4F2048AD3561AB3B5085DB242866BAD77A7E9` |

## Definition of Done

- [x] 33/33 observational and public test-feature parquets readable.
- [x] Actual rows, columns, order, names, and dtypes match schema.
- [x] Missingness, NaN, Inf, support, constants, and duplicates audited.
- [x] Conceptual/observed mapping valid for 33/33 scenes.
- [x] DAG, node, edge, observed/latent, and mechanism metadata valid.
- [x] Primary manifest contains exactly 135 records.
- [x] Supplementary manifest is separate and exploratory-only.
- [x] Public/grading allowlists and rejection tests implemented.
- [x] Nested 33 = 27 + 6 and split-role invariants pass.
- [x] Exact scene/task IDs and artifact hashes frozen.
- [x] `integrity_ready: true` recorded.

The next task is T05: select and freeze a CPDAG-producing SCD method compatible with the audited mixed data and heterogeneous mechanisms.
