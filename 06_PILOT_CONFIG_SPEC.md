# Suggested Pilot Configuration

```yaml
experiment:
  name: noisycausal_fourgraph_pilot_v0
  seed: 42

data:
  source: noisycausal
  dev_systems: 10
  holdout_systems: 40
  observational_sample_size: 2000
  sensitivity_sample_sizes: [500, 10000]
  require_resampleable_scm: true

graphs:
  methods: [llm, scd, hybrid, oracle]

  llm:
    oracle_access: false
    semantic_input: true
    observational_table: false
    temperature: 0

  scd:
    oracle_access: false
    semantic_input: false
    anonymize_columns: true
    primary_algorithm: TBD_AFTER_DATA_AUDIT

  hybrid:
    oracle_access: false
    semantic_input: true
    observational_table: true
    strategy: confidence_gated_scd_plus_llm
    edge_stability_threshold: TBD_ON_DEV

  oracle:
    source: ground_truth_graph

reasoner:
  model: TBD_STABLE_VERSION
  temperature: 0
  graph_encoding: canonical_sorted_edge_list
  prompt_version: v1
  main_repeats: 1
  stability_subset_fraction: 0.2
  stability_repeats: 3

evaluation:
  graph_built_from: clean_evidence
  conditions: [clean, IV, CS, CI]

metrics:
  structural:
    - skeleton_f1
    - directed_edge_f1
    - orientation_accuracy
    - shd
  causal_graph:
    - sid_if_compatible
    - aid_if_compatible
  downstream:
    - accuracy
    - accuracy_by_query_type
    - robustness_drop
    - oracle_gap

statistics:
  bootstrap_unit: system_id
  bootstrap_reps: 5000
  paired_binary_test: mcnemar
  multiple_testing: benjamini_hochberg
  correlation: spearman

logging:
  raw_prompts: true
  raw_outputs: true
  graph_hashes: true
  prompt_hashes: true
  tokens: true
  latency: true
```

## Freeze rule

After holdout starts, freeze:
- system IDs;
- prompts;
- SCD algorithm/config;
- hybrid thresholds;
- graph encoding;
- reasoner model/version;
- parser;
- metrics.

Any change creates a new experiment version.
