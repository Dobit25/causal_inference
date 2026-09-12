import ast
import json
from pathlib import Path

import pytest
import yaml

from fourgraph.holdout_freeze import CONDITIONS, TASKS, build_t13

ROOT = Path(__file__).resolve().parents[1]


def test_t13_generated_artifacts_are_byte_exact():
    artifacts = build_t13(ROOT, ROOT / "configs/t13_holdout_freeze.yaml")
    assert all((ROOT / path).read_bytes() == payload for path, payload in artifacts.items())


def test_t13_freezes_nested_holdout_without_opening_it():
    audit = json.loads((ROOT / "data/manifests/t13_holdout_execution_audit.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "data/manifests/t13_holdout_execution.json").read_text(encoding="utf-8"))
    assert manifest["graph_conditions"] == CONDITIONS
    assert manifest["cohorts"]["primary_downstream"]["tasks"] == TASKS
    assert audit["expected_counts"]["primary_downstream_records"] == 500
    assert audit["expected_counts"]["supplementary_reasoner_records"] == 0
    assert audit["schema_validation"] == "builtin_closed_top_level_contract_passed"
    assert audit["scope"]["api_calls"] == 0
    assert audit["scope"]["holdout_content_artifacts_read"] == []
    assert audit["scope"]["gold_answers_read"] is False
    assert audit["scope"]["oracle_edges_read"] is False
    assert audit["scope"]["accuracy_results_created"] is False
    assert audit["scope"]["holdout_accessed"] is False
    assert audit["verdict"]["t14_authorized"] is True
    assert audit["verdict"]["t14_started"] is False


def test_t13_module_has_no_live_or_data_loader_imports():
    tree = ast.parse((ROOT / "src/fourgraph/holdout_freeze.py").read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = {"openai", "google.genai", "fourgraph.causalds_public", "fourgraph.causalds_oracle", "fourgraph.causalds_scd"}
    assert imports.isdisjoint(forbidden)


def test_t13_declares_only_the_known_historical_source_drift():
    manifest = json.loads((ROOT / "data/manifests/t13_holdout_execution.json").read_text(encoding="utf-8"))
    assert manifest["legacy_replay_disclosure"]["historical_source_anchor_drift"] == {
        "T08": ["src/fourgraph/llm_backend.py"],
        "T09": ["src/fourgraph/causalds_scd.py"],
        "T10": ["src/fourgraph/graph_contract.py", "src/fourgraph/llm_backend.py"],
        "T11": ["src/fourgraph/graph_contract.py"],
    }


def test_t13_rejects_a_model_declaration_that_differs_from_frozen_t12(tmp_path):
    config = yaml.safe_load((ROOT / "configs/t13_holdout_freeze.yaml").read_text(encoding="utf-8"))
    config["frozen_protocol"]["reasoner"]["model_snapshot"] = "changed-model"
    candidate = tmp_path / "changed.yaml"
    candidate.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError, match="reasoner protocol drift"):
        build_t13(ROOT, candidate)
