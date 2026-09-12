# Experiment Configuration Specification

Two canonical configs are maintained:

- `configs/p0_released.yaml`: released CausalDS exploratory pilot.
- `configs/p1_fresh.yaml`: fresh homogeneous primary study.

## P0 frozen design

```yaml
experiment: causalds_released_p0_v1
source: pinned CausalDS GitHub/Hugging Face revisions
cohorts:
  graph: 33 clean, no-latent scenes; T04-frozen split 8/25
  primary_downstream: 27 graph scenes x 5 frozen tasks; T04-frozen split 7/20
  supplementary: 6 graph scenes; T04-frozen split 1/5; exploratory only
nesting: primary_downstream and supplementary partition graph; one split role per scene
tasks: 2–5 contract; primary uses the same frozen five-task priority
scd_primary_output: CPDAG
scd_method: BOSS + BasisFunctionBicScore
scd_parameters: {penalty_discount: 1.0, truncation_limit: 3, num_starts: 1}
cpdag_reasoning: conservative invariance
ambiguous_answer: undetermined
dag_projection: deterministic consistent extension, sensitivity only
hybrid: SCD skeleton + semantic orientation
reasoner_evidence: graph + query + non-causal glossary
graph_contract: fourgraph.graph.v1
variable_map_contract: fourgraph.variable_map.v1
reasoner_graph_view: fourgraph.reasoner_graph.v1; structure only; provenance blind
graph_hashes: structure-only graph_sha256 + full artifact_sha256
statistics: paired scene-clustered bootstrap
outcomes: co-equal exploratory by phase
```

All 33 scenes support graph-level evaluation. Primary downstream accuracy uses only the homogeneous `27 x 5` panel; the 6 supplementary scenes are reported separately and never pooled into it. T03 records the historical provisional allocation in `data/manifests/p0_provisional_split.json`; T04 verified all scenes and froze the unchanged IDs in `data/manifests/p0_frozen_split.json`.

T05 passed the deliberate mixed-data/mechanism gate and froze `BOSS + BasisFunctionBicScore` (`penalty_discount=1.0`, `truncation_limit=3`, one deterministic data-order start). Its raw CPDAG is primary; the lexicographic Dor--Tarsi consistent extension is sensitivity only. Selection evidence is in `data/manifests/p0_scd_selection.json` and `reports/t05_scd_method_selection.md`.

T06 froze the shared graph boundary in `configs/graph_contract_v1.yaml`. JSON Schemas describe record shape; `fourgraph.graph_contract` enforces graph semantics, evidence separation, hashes, and projection/Hybrid parent relationships. The T06 manifest and byte-reproducible examples are in `data/manifests/graph_contract_v1.json`.

T07 freezes `configs/t07_oracle_loader.yaml`. `GradingPurpose.ORACLE` may read only `ground_truth.json`; the loader maps public schema order to canonical IDs and emits `fourgraph.graph.v1` without returning the grading document. The development-only, edge-free audit is `data/manifests/t07_oracle_loader_audit.json`; holdout Oracle loading remains deferred.

T08 is specified in `configs/t08_llm_graph_builder.yaml`. Its loader permits only public `story.md` and `schema.json`; its frozen prompt requires exactly one decision for every unordered node pair, and only a strict acyclic result may enter `fourgraph.graph.v1`. The pinned OpenAI Responses snapshot `gpt-5.4-nano-2026-03-17` generated 8/8 valid development DAGs in one attempt each. `data/manifests/t08_llm_graph_builder_audit.json` records the provider/config/hash evidence and `llm_graph_builder_ready: true`; raw calls remain outside Git and holdout remains unopened.

T09 is frozen in `configs/t09_scd_graph_builder.yaml`. It reruns only `boss_basis_bic__p1__t3` from clean same-scene observations, emits eight primary CPDAGs plus eight sensitivity-only deterministic projections, and records parent hashes and every arbitrary orientation. `data/manifests/t09_scd_graph_builder_audit.json` reports `scd_graph_builder_ready: true`; all three T09 outputs reproduce byte-for-byte and holdout remains unopened.

T10 is frozen in `configs/t10_hybrid_graph_builder.yaml`. It takes only the raw T09 CPDAG and public semantics, reuses the exact T08 OpenAI configuration, and orients every unresolved edge without changing adjacency, compelled directions, or equivalence class. The 8/8 development Hybrid DAGs and 27 edge audits replay byte-for-byte; holdout remains unopened.

T11 is frozen in `configs/t11_graph_metrics.yaml`. It evaluates five graph views per development scene through `GraphArtifact.metrics_view()`, uses grading-only Oracle graphs in memory, records 40 per-scene results, and never coerces raw CPDAGs into DAGs. Projected SCD is sensitivity-only; SID/AID are null/unavailable pending a pinned validated implementation.

## P1 frozen design

```yaml
experiment: causalds_fresh_homogeneous_p1_v1
scenes: 100
split: 20 development / 80 holdout
nodes: stratified 5–7
SCM: linear, acyclic, non-Gaussian, causally sufficient
SCD: DirectLiNGAM
primary_N: 2000
sensitivity_N: [500, 10000] on 20 scenes
tasks: same adjustment/control contract
graph_contract: same fourgraph.graph.v1 interface as P0
statistics: paired scene-clustered bootstrap
```

Nonlinear additive-noise SCMs are a later robustness version, never silently mixed into the linear P1 result.

## Configuration freeze

Before any holdout run, freeze:

- source/generator revisions;
- scene and task IDs;
- SCD algorithm/config;
- CPDAG semantics and projection rule;
- hybrid policy;
- reasoner model snapshot and prompts;
- graph serialization;
- parsers and scorers;
- statistical analysis and exclusion rules.

Any change after holdout begins requires a new experiment name/version and a complete audit trail.
