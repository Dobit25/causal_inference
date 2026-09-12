# Metrics and Statistics Protocol

## Layer 1 — Graph quality

### Metrics valid for all graph conditions

- Skeleton precision, recall, and F1.
- Adjacency false-positive/false-negative counts.
- Graph validity and node-set consistency.

Metrics must consume `GraphArtifact.metrics_view()` so every method is compared on the same normalized `PartialGraph`. They may use method/view labels to choose a valid metric family, but never silently coerce a raw CPDAG into a DAG.

### Raw CPDAG metrics

- Correct compelled orientations.
- Incorrect compelled orientations.
- Unresolved orientation rate.
- CPDAG-compatible skeleton SHD.

Do not count an undirected CPDAG edge as an ordinary directed error without reporting that convention.

### DAG metrics

For `G_LLM`, `G_HYBRID`, `G_ORACLE`, P1 SCD DAG, and P0 projected-DAG sensitivity:

- Directed-edge precision, recall, and F1.
- Orientation accuracy conditional on correct adjacency.
- SHD and normalized SHD.

Clearly label projected-DAG metrics; arbitrary compatible orientations are not raw SCD discoveries.

## Layer 2 — Causal-functional quality

- SID only for compatible DAG node sets and implementations.
- AID only after graph-type compatibility is established.
- Query-relevant structural error as an explicitly exploratory project metric.

Outcome E is unavailable rather than zero when SID/AID assumptions are not satisfied.

T11 freezes the concrete structural conventions: skeleton SHD is adjacency FP + FN; DAG SHD is an unordered-pair state mismatch with reversal cost one; CPDAG state SHD distinguishes absent, undirected, forward, and reverse; normalized SHD divides by `n choose 2`; floating summaries use eight decimal places. SID/AID are currently `unavailable` with null values because no implementation has yet been pinned and validated. Raw CPDAGs are never silently projected.

The completed development evaluation contains 40 records (8 scenes × 5 graph views). These results are descriptive only and cannot be used to reopen T08–T10. Full scene-level inference remains deferred to T15.

## Layer 3 — Downstream utility

### Oracle-answer accuracy

Scores the reasoner's answer against the scene's ground-truth task answer.

For adjustment tasks, official CausalDS scoring remains primary for benchmark comparability. T12 v2 adds a separately labelled Pearl back-door total-effect sensitivity: controls may not be descendants of treatment and d-separation is evaluated after removing treatment's outgoing arrows. The bespoke `forbidden_controls_list` task is not assigned a standards-based value because the constructs are not equivalent.

### Uncertainty-aware correctness

- If all CPDAG-compatible DAG extensions imply the same answer, that invariant answer is correct.
- If compatible extensions imply different answers, `undetermined` is correct.
- A definitive answer in an ambiguous case is uncertainty-incorrect even if it coincides with the oracle DAG by chance.

### Derived summaries

```text
OracleGap(method) = Accuracy(G_ORACLE) - Accuracy(G_method)
ResidualOracleError = 1 - Accuracy(G_ORACLE)
```

Report task-type results and scene-macro results. Never retain aggregate accuracy without per-scene/task records.

## Independent unit and aggregation

The independent statistical unit is `scene_id`. Tasks and graph methods are repeated measurements within a scene.

Use all 33 graph-cohort scenes for graph-level metrics. Compute primary downstream summaries only on the fixed 27-scene, five-task panel. Report the 6 supplementary scenes separately as exploratory cases; do not pool their available tasks into primary accuracy.

First compute:

\[
Accuracy_{s,m}=\frac{1}{T_s}\sum_t Correct_{s,t,m}.
\]

Then aggregate scenes with equal weight. Do not treat `scene × task × graph` rows as independent samples.

## Inference

- Primary uncertainty: paired scene-clustered bootstrap.
- Bootstrap resampling unit: complete scene, retaining every task and graph condition.
- Repetitions: 5000 unless an experiment version declares otherwise.
- McNemar: sensitivity only because ordinary task-level McNemar ignores scene clustering.
- Correlation: Spearman with scene-clustered uncertainty or method-specific scene-level analysis.
- Multiple testing: Benjamini–Hochberg within each declared phase/outcome family.

## Outcome policy

A–G are co-equal exploratory research outcomes, evaluated only in applicable phases. Report estimates and intervals even when non-significant or adverse. GO/REFINE/STOP is based on data integrity, graph variance, reasoner responsiveness, scoring validity, and reproducibility—not on manufacturing a positive result.

## Required record

```json
{
  "scene_id": "...",
  "task_id": "...",
  "graph_method": "llm|scd|hybrid|oracle",
  "graph_view": "cpdag|projected_dag|dag",
  "graph_schema_version": "fourgraph.graph.v1",
  "variable_mapping_sha256": "...",
  "graph_sha256": "...",
  "graph_artifact_sha256": "...",
  "prompt_hash": "...",
  "model_id": "...",
  "raw_output": "...",
  "parsed_answer": "...",
  "gold_answer": "...",
  "oracle_answer_correct": true,
  "uncertainty_aware_correct": true,
  "latency_ms": null,
  "input_tokens": null,
  "output_tokens": null,
  "retry_count": 0
}
```
