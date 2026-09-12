# T11 — Development graph metrics

## Outcome

T11 is complete for all eight frozen graph-development scenes. It evaluated five graph views per scene—`G_LLM`, raw `G_SCD`, projected `G_SCD`, `G_HYBRID`, and grading-only `G_ORACLE`—and emitted 40 canonical per-scene records. No LLM call, task/query access, builder tuning, or holdout access occurred. Oracle DAGs were loaded only in memory through the T07 grading capability; versioned outputs contain hashes and metrics, not Oracle edge lists.

## Frozen conventions

- All structural inputs use `GraphArtifact.metrics_view()` with exact scene/node alignment.
- Skeleton SHD is `false_positive + false_negative`.
- DAG SHD compares unordered-pair states; a reversal costs one operation.
- CPDAG state SHD distinguishes absent, undirected, forward, and reverse states.
- SHD normalization divides by `n choose 2`.
- Raw CPDAGs are never silently projected for DAG-only metrics.
- Projected SCD is explicitly sensitivity-only; `G_ORACLE` is a sanity condition.
- Aggregates are equal-weight scene macros, not 40 independent observations.

SID and AID remain unavailable because T11 has no pinned, validated implementation. Their values are recorded as `null`, never zero. This does not block the mandatory structural evaluation.

## Development-only descriptive results

| Condition | Role | Skeleton F1 | Skeleton precision | Skeleton recall | DAG directed F1 | Common-adjacency orientation accuracy | Raw unresolved rate |
|---|---|---:|---:|---:|---:|---:|---:|
| `G_LLM` | primary | 1.000 | 1.000 | 1.000 | 0.975 | 0.975 | — |
| `G_SCD_RAW` | primary CPDAG | 0.959 | 0.931 | 1.000 | — | — | 0.900 |
| `G_SCD_PROJECTED` | sensitivity | 0.959 | 0.931 | 1.000 | 0.225 | 0.234 | — |
| `G_HYBRID` | primary | 0.959 | 0.931 | 1.000 | 0.918 | 0.958 | — |
| `G_ORACLE` | sanity | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | — |

Raw SCD's four predicted compelled edges were all correct relative to the Oracle CPDAG. Across scenes it inherited three false-positive adjacencies and no false-negative adjacency. Of 27 unresolved SCD edges, 24 corresponded to true Oracle adjacencies and three were inherited false positives.

On the 24 evaluable unresolved edges:

- Hybrid semantic orientation: 23 correct, 1 incorrect;
- deterministic projection: 5 correct, 19 incorrect;
- semantic and projection decisions differed on 18 edges;
- semantics improved on projection for 18 edges and worsened it for none.

These results are descriptive development diagnostics, not inferential findings. The small development set and near-ceiling `G_LLM`/Hybrid orientation results may indicate easy semantic stories. T08–T10 remain unchanged; significance testing and full graph-cohort analysis are deferred until the frozen holdout workflow.

## Reproducibility

```powershell
conda run -n cau python scripts/evaluate_causalds_t11.py <extracted-causalds-source-root>
conda run -n cau python scripts/evaluate_causalds_t11.py <extracted-causalds-source-root> --check
```

Freeze hashes:

- config: `C49EACA54BBD9F5218C768DCD16F5F0CFDCC8B1514166F12D225D1DC6280A6E2`;
- metric records: `96FC8C99E19EBA11F2F8177DC744769D93F5662A6AAE1E9DE0D3A5C6106F7A9D`;
- audit: `B0CEC26D62F37018A6E61839860E44F24E8F6E05D9355DA81F9BC6595291CC10`.

T12 can now implement the fixed reasoner and task scorers without changing the graph builders or T11 conventions.
