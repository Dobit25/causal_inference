import ast
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_t17_freezer_is_offline():
    tree = ast.parse((ROOT / "scripts/freeze_t17_p1_hybrid_protocol.py").read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "openai" not in imports
    assert "fourgraph.openai_backend" not in imports
    assert "fourgraph.t10_openai_backend" not in imports
    assert "fourgraph.t12_openai_backend" not in imports


def test_t17_protocol_has_fixed_scope_and_no_execution_authority():
    protocol = yaml.safe_load((ROOT / "configs/p1_hybrid_v1.yaml").read_text(encoding="utf-8"))
    assert protocol["generation"]["scene_count"] == 100
    assert protocol["generation"]["split"]["development"] == 20
    assert protocol["generation"]["split"]["holdout"] == 80
    assert protocol["semantic_evidence"]["variants"] == ["full", "partial", "ambiguous"]
    assert sum(protocol["generation"]["graph"]["primary_motif_allocation"].values()) == 100
    assert sum(protocol["generation"]["scm"]["exogenous_noise_family_allocation"]) == 100
    assert protocol["semantic_evidence"]["partial"]["selected_edge_count"] == "round_half_up_half_of_true_edge_count"
    assert protocol["graph_views"]["scheduled_counts"]["downstream_tasks_total"] == 5500
    assert protocol["semantic_backend"]["live_calls_authorized_at_T17"] is False
    assert protocol["reasoner"]["live_calls_authorized_at_T17"] is False
    assert protocol["access_and_freeze"]["P1_holdout_execution_authorized"] is False


def test_t17_manifest_is_a_pre_generation_freeze():
    path = ROOT / "data/manifests/t17_p1_hybrid_protocol_freeze.json"
    assert path.exists()
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["verdict"]["t17_complete"] is True
    assert audit["verdict"]["p1_hybrid_protocol_frozen"] is True
    assert audit["verdict"]["t18_generator_inventory_authorized"] is True
    assert audit["verdict"]["live_model_calls_authorized"] is False
    assert audit["verdict"]["H2_implementation_authorized"] is False
    assert audit["evidence_boundary"]["generated_scenes"] == 0
    assert audit["evidence_boundary"]["holdout_accessed"] is False
    dependencies = {item["path"] for item in audit["dependencies"]}
    assert "configs/p1_fresh.yaml" in dependencies
    assert audit["unresolved_until_registered_stage"]["semantic_preference_prompt_hash"] == "T20"
