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


def test_roles_are_disjoint_and_counts_are_frozen_without_materialization():
    design = _json("data/manifests/p1_v3_cohort_design.json")
    assert design["cohorts_materialized"] is False
    assert design["scene_ids_materialized"] is False
    assert design["new_scene_count"] == 840
    roles = design["roles"]
    assert roles["method_development"]["scene_count"] == 40
    assert roles["semantic_calibration"]["scene_count"] == 400
    assert roles["threshold_validation"]["scene_count"] == 400
    assert roles["existing_final_holdout"]["scene_count"] == 80
    namespaces = {
        roles[name]["namespace"]
        for name in ("method_development", "semantic_calibration", "threshold_validation")
    }
    seeds = {
        roles[name]["master_seed"]
        for name in ("method_development", "semantic_calibration", "threshold_validation")
    }
    assert len(namespaces) == 3 and len(seeds) == 3
    assert roles["existing_final_holdout"]["status"] == "sealed_unchanged"


def test_scene_is_inference_unit_and_familywise_budget_is_partitioned():
    config = yaml.safe_load((ROOT / "configs/p1_v3_power_cohort_design.yaml").read_text(encoding="utf-8"))
    assert config["estimands"]["independent_unit"] == "scene"
    assert config["estimands"]["reporting_weights"]["primary"] == "mean_within_scene_error_fraction"
    family = config["familywise_risk"]
    assert sum(family["allocation"].values()) == family["total_failure_probability_delta"]
    assert family["semantic_groups"] == 6
    assert family["threshold_candidates"] == 15
    assert family["cluster_handling"]["within_scene_edges_never_treated_as_independent"] is True


def test_prospective_power_meets_registered_target_and_is_not_observed_result():
    power = _json("data/manifests/p1_v3_prospective_power.json")
    assert power["design_inputs_not_observed_results"] is True
    assert power["selected_scene_counts"] == {
        "method_development": 40,
        "semantic_calibration": 400,
        "threshold_validation": 400,
    }
    calibration = power["risk_power"]["semantic_calibration"]
    validation = power["risk_power"]["threshold_validation"]
    assert calibration["independent_scenes"] == 280
    assert validation["independent_scenes"] == 340
    assert calibration["power_by_true_error"]["0.010"] >= 0.80
    assert validation["power_by_true_error"]["0.010"] >= 0.80
    assert power["coverage_power"]["power_by_true_coverage"]["0.30"] >= 0.80


def test_calibration_and_validation_cannot_leak_roles():
    design = _json("data/manifests/p1_v3_cohort_design.json")
    roles = design["roles"]
    assert roles["semantic_calibration"]["may_select_threshold"] is False
    assert roles["threshold_validation"]["may_certify_semantic_groups"] is False
    stages = design["stage_boundaries"]
    assert stages["calibration"]["cannot_select_statistical_threshold"] is True
    assert stages["validation"]["no_safe_candidate"] == "stop_without_final_holdout"
    assert stages["final_holdout"]["remains_unauthorized_by_this_design"] is True


def test_resource_envelope_is_prospective_only():
    design = _json("data/manifests/p1_v3_cohort_design.json")
    envelope = design["resource_envelope"]
    assert envelope["bootstrap_boss_runs_if_all_new_cohorts_later_authorized"] == 168000
    assert envelope["semantic_whole_graph_calls_if_all_new_cohorts_later_authorized"] == 15120
    audit = _json("data/manifests/p1_v3_power_cohort_design_audit.json")
    boundary = audit["evidence_boundary"]
    assert boundary == {
        "bootstrap_or_boss_runs": 0,
        "final_holdout_accessed": False,
        "historical_cohorts_accessed": False,
        "power_simulation_only": True,
        "semantic_api_calls": 0,
        "successor_observations_created": 0,
        "successor_scene_records_created": 0,
    }
    assert audit["authorization"]["successor_cohort_generation"] is False
    assert audit["authorization"]["generator_implementation_and_synthetic_conformance"] is True


def test_audit_hashes_match():
    audit = _json("data/manifests/p1_v3_power_cohort_design_audit.json")
    for record in audit["dependencies"]:
        assert record["sha256"] == _hash(record["path"])
    assert audit["implementation"]["sha256"] == _hash(audit["implementation"]["path"])
    for record in audit["outputs"]:
        assert record["sha256"] == _hash(record["path"])
        assert record["bytes"] == (ROOT / record["path"]).stat().st_size
