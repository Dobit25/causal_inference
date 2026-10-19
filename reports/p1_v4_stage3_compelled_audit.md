# P1V4 compelled-direction semantic audit

{
  "task": "P1_V4_STAGE_3D_MINI_MEDIUM_COMPELLED_DIRECTION_SEMANTIC_AUDIT",
  "status": "PASS_DEVELOPMENT_ONLY",
  "retrospective_oracle_metric": true,
  "results": {
    "Constrained-BOSS/full": {
      "baseline_total": 113,
      "baseline_correct": 86,
      "baseline_precision": 0.7610619469026548,
      "confirmed": 83,
      "confirmed_correct": 83,
      "confirmed_precision": 1.0,
      "retention": 0.7345132743362832,
      "statuses": {
        "SEMANTIC_CONFIRMED": 83,
        "SEMANTIC_CONFLICT": 24,
        "SEMANTIC_UNRESOLVED": 4,
        "SEMANTIC_ABSTAIN": 2
      }
    },
    "Constrained-BOSS/partial": {
      "baseline_total": 113,
      "baseline_correct": 86,
      "baseline_precision": 0.7610619469026548,
      "confirmed": 52,
      "confirmed_correct": 52,
      "confirmed_precision": 1.0,
      "retention": 0.46017699115044247,
      "statuses": {
        "SEMANTIC_UNRESOLVED": 50,
        "SEMANTIC_CONFIRMED": 52,
        "SEMANTIC_CONFLICT": 11
      }
    },
    "Constrained-FGES/full": {
      "baseline_total": 112,
      "baseline_correct": 82,
      "baseline_precision": 0.7321428571428571,
      "confirmed": 80,
      "confirmed_correct": 80,
      "confirmed_precision": 1.0,
      "retention": 0.7142857142857143,
      "statuses": {
        "SEMANTIC_CONFIRMED": 80,
        "SEMANTIC_CONFLICT": 25,
        "SEMANTIC_ABSTAIN": 3,
        "SEMANTIC_UNRESOLVED": 4
      }
    },
    "Constrained-FGES/partial": {
      "baseline_total": 112,
      "baseline_correct": 82,
      "baseline_precision": 0.7321428571428571,
      "confirmed": 46,
      "confirmed_correct": 46,
      "confirmed_precision": 1.0,
      "retention": 0.4107142857142857,
      "statuses": {
        "SEMANTIC_UNRESOLVED": 53,
        "SEMANTIC_CONFIRMED": 46,
        "SEMANTIC_CONFLICT": 13
      }
    }
  },
  "groups_sha256": "DDDAA24961880E376111EF9FFA9EA87715453BA1426E0603371E2F9AC27970C8",
  "raw_sha256": "6045364717823DBC9427C9B107DC8984039483CF38A13340B8E5384C64A534AC",
  "oracle_scope": "P1V4SD000-P1V4SD029 only",
  "semantic_api_calls": 360,
  "holdout_access": 0,
  "closure": 0
}