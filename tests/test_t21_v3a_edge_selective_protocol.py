from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def protocol() -> dict:
    return yaml.safe_load((ROOT / "configs/p1_edge_selective_v2.yaml").read_text(encoding="utf-8"))


def test_v3a_freezer_is_offline_and_does_not_open_generated_scenes() -> None:
    source = (ROOT / "scripts/freeze_t21_v3a_edge_selective_protocol.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "openai" not in imports
    assert "google" not in imports
    assert ".glob(" not in source
    assert ".rglob(" not in source
    assert "np.load" not in source
    assert "data/generated" in source and "results/raw" in source  # dependency guard rejects both


def test_v3a_scope_preserves_boss_structure() -> None:
    p = protocol()
    parent = p["parent_graph"]
    assert parent["mutable_edge_class"] == "undirected_only"
    assert parent["preserve_skeleton"] is True
    assert parent["preserve_compelled_directions"] is True
    assert parent["add_edges"] is False
    assert parent["delete_edges"] is False
    assert parent["reverse_compelled_edges"] is False


def test_v3a_consensus_and_partial_graph_contract_are_exact() -> None:
    p = protocol()
    consensus = p["credible_extension_consensus"]
    assert consensus["enumeration"] == "exact"
    assert consensus["normalization"] == {
        "method": "stable_softmax_over_all_extension_scores",
        "temperature": 1.0,
        "temperature_tuning_allowed": False,
    }
    assert consensus["joint_selection"]["greedy_order_dependence_allowed"] is False
    output = p["partial_graph_output"]
    assert output["closure"]["method"] == "meek_rules_R1_R2_R3_R4"
    assert output["direction_sources"] == ["compelled", "semantic_selected", "closure_propagated", "unresolved"]
    assert len(output["invariants"]) == 6


def test_v3a_threshold_grid_and_gate_are_frozen() -> None:
    selection = protocol()["threshold_selection"]
    assert selection["grid"]["semantic_confidence"] == [0.8, 0.9, 0.95, 0.99, 0.999]
    assert selection["grid"]["global_stability"] == [0.8, 0.9, 0.95, 1.0]
    assert selection["candidates"] == 20
    assert selection["gate"] == {
        "graph_validity": 1.0,
        "end_to_end_selective_orientation_precision_minimum": 0.95,
        "minimum_answered_edges": 20,
        "minimum_orientation_coverage": 0.2,
    }
    assert selection["downstream_results_allowed_for_selection"] is False


def test_v3a_metric_contract_penalizes_oriented_false_adjacencies() -> None:
    metrics = protocol()["metric_contract"]
    assert metrics["answered_direction_definition"] == {
        "include": ["semantic_selected", "closure_propagated"],
        "exclude": ["parent_compelled", "unresolved"],
    }
    assert metrics["primary_precision"]["false_adjacency_orientation"] == "incorrect"
    assert metrics["coverage"]["denominator"] == "all_parent_undirected_edges_including_false_adjacencies"


def test_v3a_uses_new_validation_and_keeps_existing_holdout_sealed() -> None:
    cohorts = protocol()["cohorts"]
    assert cohorts["method_development"]["threshold_selection_allowed"] is False
    validation = cohorts["threshold_validation"]
    assert validation["count"] == 20
    assert validation["master_seed"] == 21301
    assert validation["generated_at_v3a"] is False
    assert validation["method_executed_at_v3a"] is False
    assert cohorts["final_holdout"] == {
        "source": "existing_T18_holdout_80",
        "count": 80,
        "exact_ids_unchanged": True,
        "accessed_at_v3a": False,
        "access_authorized": False,
    }


def test_v3a_manifest_is_design_only_and_fail_closed() -> None:
    audit = json.loads((ROOT / "data/manifests/t21_v3a_edge_selective_protocol_freeze.json").read_text(encoding="utf-8"))
    assert audit["verdict"] == {
        "live_model_calls_authorized": False,
        "p1_holdout_authorized": False,
        "p1_v2_edge_selective_protocol_frozen": True,
        "t21_v3a_complete": True,
        "t21_v3b_offline_implementation_authorized": True,
        "t22_authorized": False,
        "validation_generation_authorized": False,
    }
    assert audit["evidence_boundary"]["api_calls"] == 0
    assert audit["evidence_boundary"]["validation_scenes_generated"] == 0
    assert audit["evidence_boundary"]["holdout_scene_artifacts_accessed"] == 0
    assert audit["design_summary"]["threshold_candidates"] == 20
