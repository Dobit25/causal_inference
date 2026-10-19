# P1V4 parent CPDAG + semantic-selected metrics

Development-only Oracle diagnostic. The integrated graph includes parent compelled directions and condition-specific `VERY_HIGH/HIGH` semantic-selected directions; no Meek closure was applied.

```json
{
  "nano_medium": {
    "Constrained-BOSS": {
      "parent_compelled": {
        "published": 113,
        "correct": 86,
        "wrong": 27,
        "precision": 0.7610619469026548
      },
      "full": {
        "semantic_selected": {
          "published": 59,
          "correct": 59,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.5841584158415841,
        "end_to_end_partial_graph": {
          "published": 172,
          "correct": 145,
          "wrong": 27,
          "precision": 0.8430232558139535,
          "unresolved_parent_edges": 42,
          "unresolved_fraction_of_parent_undirected": 0.4158415841584159
        },
        "parent_undirected_edges": 101,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 2,
        "out_of_parent_directions_filtered": 16
      },
      "partial": {
        "semantic_selected": {
          "published": 39,
          "correct": 39,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.38613861386138615,
        "end_to_end_partial_graph": {
          "published": 152,
          "correct": 125,
          "wrong": 27,
          "precision": 0.8223684210526315,
          "unresolved_parent_edges": 62,
          "unresolved_fraction_of_parent_undirected": 0.6138613861386139
        },
        "parent_undirected_edges": 101,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 1,
        "out_of_parent_directions_filtered": 9
      }
    },
    "Constrained-FGES": {
      "parent_compelled": {
        "published": 112,
        "correct": 82,
        "wrong": 30,
        "precision": 0.7321428571428571
      },
      "full": {
        "semantic_selected": {
          "published": 57,
          "correct": 57,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.59375,
        "end_to_end_partial_graph": {
          "published": 169,
          "correct": 139,
          "wrong": 30,
          "precision": 0.8224852071005917,
          "unresolved_parent_edges": 39,
          "unresolved_fraction_of_parent_undirected": 0.40625
        },
        "parent_undirected_edges": 96,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 4,
        "out_of_parent_directions_filtered": 10
      },
      "partial": {
        "semantic_selected": {
          "published": 36,
          "correct": 36,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.375,
        "end_to_end_partial_graph": {
          "published": 148,
          "correct": 118,
          "wrong": 30,
          "precision": 0.7972972972972973,
          "unresolved_parent_edges": 60,
          "unresolved_fraction_of_parent_undirected": 0.625
        },
        "parent_undirected_edges": 96,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 2,
        "out_of_parent_directions_filtered": 8
      }
    }
  },
  "mini_medium": {
    "Constrained-BOSS": {
      "parent_compelled": {
        "published": 113,
        "correct": 86,
        "wrong": 27,
        "precision": 0.7610619469026548
      },
      "full": {
        "semantic_selected": {
          "published": 78,
          "correct": 78,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.7722772277227723,
        "end_to_end_partial_graph": {
          "published": 191,
          "correct": 164,
          "wrong": 27,
          "precision": 0.8586387434554974,
          "unresolved_parent_edges": 23,
          "unresolved_fraction_of_parent_undirected": 0.2277227722772277
        },
        "parent_undirected_edges": 101,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 4,
        "out_of_parent_directions_filtered": 17
      },
      "partial": {
        "semantic_selected": {
          "published": 48,
          "correct": 48,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.4752475247524752,
        "end_to_end_partial_graph": {
          "published": 161,
          "correct": 134,
          "wrong": 27,
          "precision": 0.8322981366459627,
          "unresolved_parent_edges": 53,
          "unresolved_fraction_of_parent_undirected": 0.5247524752475248
        },
        "parent_undirected_edges": 101,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 1,
        "out_of_parent_directions_filtered": 10
      }
    },
    "Constrained-FGES": {
      "parent_compelled": {
        "published": 112,
        "correct": 82,
        "wrong": 30,
        "precision": 0.7321428571428571
      },
      "full": {
        "semantic_selected": {
          "published": 67,
          "correct": 67,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.6979166666666666,
        "end_to_end_partial_graph": {
          "published": 179,
          "correct": 149,
          "wrong": 30,
          "precision": 0.8324022346368715,
          "unresolved_parent_edges": 29,
          "unresolved_fraction_of_parent_undirected": 0.30208333333333337
        },
        "parent_undirected_edges": 96,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 6,
        "out_of_parent_directions_filtered": 20
      },
      "partial": {
        "semantic_selected": {
          "published": 46,
          "correct": 46,
          "wrong": 0,
          "precision": 1.0
        },
        "semantic_selected_coverage_of_parent_undirected": 0.4791666666666667,
        "end_to_end_partial_graph": {
          "published": 158,
          "correct": 128,
          "wrong": 30,
          "precision": 0.810126582278481,
          "unresolved_parent_edges": 50,
          "unresolved_fraction_of_parent_undirected": 0.5208333333333333
        },
        "parent_undirected_edges": 96,
        "parent_fail_closed": 0,
        "global_conflict_fail_closed": 2,
        "out_of_parent_directions_filtered": 8
      }
    }
  }
}
```
