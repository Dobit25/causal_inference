# P1V4 final architecture before independent calibration

{
  "architecture": {
    "primary_parent": "Constrained-BOSS",
    "robustness_parent": "Constrained-FGES",
    "semantic_input_pool": "union_of_primary_and_robustness_parent_adjacencies",
    "maximum_pairs_per_scene": 21,
    "model_sees_statistical_parent_direction": false,
    "automatic_chunking": "forbidden",
    "closure": "forbidden",
    "parent_mutation": "forbidden",
    "output_states": [
      "confirmed_compelled",
      "semantic_selected",
      "unresolved"
    ],
    "rules": {
      "compelled": {
        "input": "parent_directed_edge",
        "publish_if": "automatic_semantic_direction_matches_parent_direction",
        "conflict_or_no_confirmation": "unresolved"
      },
      "undirected": {
        "input": "parent_undirected_edge",
        "publish_if": "automatic_semantic_direction",
        "otherwise": "unresolved"
      },
      "absent": {
        "publish": false
      }
    },
    "condition_specific_filtering": "required",
    "false_positive_adjacency_if_oriented": "counts_as_direction_error"
  },
  "calibration": {
    "independent_unit": "scene",
    "sequential_looks": [
      120,
      160,
      200,
      240,
      280,
      320,
      360,
      400,
      440
    ],
    "full_partial_certification_separate": true,
    "primary_precision": {
      "metric": "all_published_directions_combined_confirmed_compelled_and_semantic_selected",
      "one_sided_lower_bound": 0.95,
      "familywise_error_control": 0.025,
      "confidence_sequence": "registered_scene_level_confidence_sequence"
    },
    "coverage": {
      "metric": "published_directions_divided_by_primary_parent_adjacencies",
      "minimum_scene_mean": 0.2
    },
    "graph_validity": 1.0,
    "high_guardrail": {
      "applies_to": "all_High_agreement_published_directions_by_source_and_variant",
      "precision_lower_bound": 0.9,
      "minimum_contributing_scenes": 60,
      "insufficient_evidence": "High_review_only",
      "systematic_failure": "stop_before_validation"
    },
    "ambiguous_diagnostic": {
      "role": "abstention_only",
      "compelled_edges_included": false
    },
    "nonedge_diagnostic": {
      "role": "hallucination_only",
      "threshold_selection_role": "none"
    }
  },
  "development_only_caveat": "The cited 30-scene results chose a candidate architecture; they are not calibration evidence."
}
