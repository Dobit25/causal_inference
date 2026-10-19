# P1V4 development scientific review

{
  "schema_version": "fourgraph.p1_v4_stage3_development_scientific_review.v1",
  "task": "P1_V4_STAGE_3D_DEVELOPMENT_SCIENTIFIC_REVIEW_AND_MODEL_POLICY_FREEZE",
  "status": "PASS_DEVELOPMENT_REVIEW_COMPLETE",
  "scope": "30 development scenes only; descriptive, not validation or holdout evidence",
  "semantic_results": {
    "nano_medium": {
      "full": {
        "automatic_semantic_selected": 116,
        "correct": 116,
        "wrong": 0,
        "precision": 1.0,
        "one_sided_95pct_wilson_lcb": 0.9772079434930377
      },
      "partial": {
        "automatic_semantic_selected": 75,
        "correct": 75,
        "wrong": 0,
        "precision": 1.0,
        "one_sided_95pct_wilson_lcb": 0.96518210498465
      },
      "all_variants": {
        "automatic_semantic_selected": 191,
        "correct": 191,
        "wrong": 0,
        "precision": 1.0,
        "one_sided_95pct_wilson_lcb": 0.9860326999121913
      }
    },
    "mini_medium": {
      "full": {
        "automatic_semantic_selected": 145,
        "correct": 145,
        "wrong": 0,
        "precision": 1.0,
        "one_sided_95pct_wilson_lcb": 0.9816828577260794
      },
      "partial": {
        "automatic_semantic_selected": 94,
        "correct": 94,
        "wrong": 0,
        "precision": 1.0,
        "one_sided_95pct_wilson_lcb": 0.972022871104802
      },
      "all_variants": {
        "automatic_semantic_selected": 239,
        "correct": 239,
        "wrong": 0,
        "precision": 1.0,
        "one_sided_95pct_wilson_lcb": 0.9888064484768044
      }
    }
  },
  "parent_compelled_precision": {
    "Constrained-BOSS": 0.7610619469026548,
    "Constrained-FGES": 0.7321428571428571
  },
  "key_findings": [
    "Both frozen models had zero errors among the automatic semantic-selected directions that survived condition-specific parent filtering.",
    "Mini-medium selected more semantic directions than Nano-medium on the same frozen inputs.",
    "Parent compelled directions have materially lower precision than semantic-selected directions; integrated partial-graph precision therefore cannot be interpreted as a semantic-model precision estimate.",
    "No-closure results are the primary development comparison; closure was not used to increase coverage."
  ],
  "limitations": [
    "The 30 scenes are method-development data and cannot certify generalization.",
    "The model choice is frozen for independent calibration, not claimed as a best-model result.",
    "Wilson lower bounds are descriptive here; sequential certification remains reserved for the independent calibration protocol."
  ],
  "next_action": "run independent calibration only after a new calibration authorization; do not tune on these 30 scenes"
}

## Frozen pre-calibration policy

{
  "schema_version": "fourgraph.p1_v4_precalibration_model_policy.v1",
  "task": "P1_V4_STAGE_3D_DEVELOPMENT_SCIENTIFIC_REVIEW_AND_MODEL_POLICY_FREEZE",
  "status": "FROZEN_CANDIDATE_POLICY_PENDING_INDEPENDENT_CALIBRATION",
  "primary_semantic_model": "gpt-5.4-mini-2026-03-17",
  "reasoning_effort": "medium",
  "selection_basis": "higher automatic semantic-selected coverage with zero direction errors on frozen development data; selection is not a generalization claim",
  "nano_medium_role": "frozen cost-sensitive comparator; not the primary calibration model",
  "semantic_selection": {
    "accepted_agreements": [
      "VERY_HIGH",
      "HIGH"
    ],
    "closure": "forbidden",
    "condition_specific_parent_filtering": true
  },
  "primary_parent": "Constrained-BOSS",
  "parent_policy": "compelled statistical directions remain separately labelled statistical context and are not automatically semantic-certified",
  "constrained_fges_role": "robustness comparator",
  "calibration_gate_unchanged": "independent sequential calibration is required before certification; no threshold change is authorized",
  "frozen_from_review_sha256": "FBABB7AE8DEB2A5B15F7EA5507F0229CE542914C32EE254652F8F6C8B061FE78"
}
