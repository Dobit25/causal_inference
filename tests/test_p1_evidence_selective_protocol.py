from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def _config():
    return yaml.safe_load((ROOT / "configs/p1_evidence_selective_v1.yaml").read_text(encoding="utf-8"))


def test_primary_method_and_execution_boundary_are_exact():
    config = _config()
    assert config["statistical_method"]["primary"] == "bootstrap_boss"
    assert config["statistical_method"]["ensemble"]["status"] == "deferred"
    assert config["statistical_method"]["observations"]["repetitions"] == 200
    assert config["statistical_method"]["observations"]["bootstrap_sample_n"] == 2000
    assert config["freeze_boundary"]["bootstrap_runs_executed"] == 0
    assert config["freeze_boundary"]["scenes_generated"] == 0
    assert config["freeze_boundary"]["semantic_api_calls"] == 0
    assert config["freeze_boundary"]["final_holdout_accessed"] is False


def test_semantic_model_whole_graph_and_six_balanced_prompts_are_frozen():
    semantic = _config()["semantic_method"]
    assert semantic["model_snapshot"] == "gpt-5.4-nano-2026-03-17"
    assert semantic["call_granularity"] == "whole_graph"
    assert semantic["calls_per_scene_story"] == 6
    assert semantic["balanced_pair_order"]["A_first"] == ["P1", "P3", "P5"]
    assert semantic["balanced_pair_order"]["B_first"] == ["P2", "P4", "P6"]
    assert semantic["automatic_orientation_eligibility"] == ["very_high", "high"]
    assert semantic["medium_action"] == "unresolved_human_review"
    assert semantic["self_reported_probability_used_as_confidence"] is False


def test_risk_control_and_no_posthoc_escape_are_frozen():
    config = _config()
    risk = config["risk_control"]
    assert risk["target_selective_error_alpha"] == 0.05
    assert risk["failure_probability_delta"] == 0.05
    assert risk["minimum_useful_coverage"] == 0.20
    assert risk["no_safe_candidate_action"] == "stop_without_retuning_or_holdout_access"
    assert config["reproducibility"]["any_post_freeze_change"] == "new_protocol_version_and_new_calibration_validation_cohorts"


def test_final_holdout_and_historical_cohorts_are_not_tuning_data():
    cohorts = _config()["cohort_protocol"]
    assert cohorts["old_method_development_20"] == "historical_diagnostic_only"
    assert cohorts["old_validation_p1v_20"] == "historical_negative_result_only"
    assert cohorts["existing_final_holdout_80"]["status"] == "sealed"
    assert cohorts["sample_size"]["exact_counts_frozen_now"] is False
    assert cohorts["no_scene_reuse_across_successor_roles"] is True


def test_freeze_manifest_pins_all_dependencies_and_authorizes_only_offline_implementation():
    audit = _json("data/manifests/p1_evidence_selective_protocol_freeze.json")
    for row in audit["dependencies"]:
        assert row["sha256"] == _hash(row["path"])
        assert row["bytes"] == (ROOT / row["path"]).stat().st_size
    assert audit["evidence_boundary"] == {
        "bootstrap_implementation_exists": False,
        "bootstrap_runs_executed": 0,
        "final_holdout_accessed": False,
        "old_development_or_validation_reanalyzed": False,
        "scenes_generated": 0,
        "semantic_api_calls": 0,
    }
    assert audit["authorization"]["next_action"] == "P1_V3_BOOTSTRAP_BOSS_OFFLINE_IMPLEMENTATION_AND_CONFORMANCE"
    assert audit["authorization"]["study_scene_bootstrap_execution"] is False
    assert audit["authorization"]["semantic_api_calls"] is False
    assert audit["authorization"]["final_holdout_access"] is False


def test_contract_schemas_are_closed_and_versioned():
    audit = _json("data/manifests/p1_evidence_selective_protocol_freeze.json")
    assert len(audit["contracts"]) == 4
    for path in (
        "schemas/statistical_edge_evidence_v1.schema.json",
        "schemas/semantic_edge_evidence_v1.schema.json",
        "schemas/semantic_whole_graph_response_v1.schema.json",
        "schemas/evidence_selective_graph_v1.schema.json",
    ):
        schema = _json(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
