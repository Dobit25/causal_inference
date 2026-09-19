from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_panel_and_schedule_arithmetic():
    design = _json("data/manifests/p1_v3_runtime_cost_pilot_design.json")
    panel = design["synthetic_panel"]
    assert panel["scene_count"] == 9
    for name in ("node_count", "primary_motif", "noise_family", "query_stratum"):
        assert sum(panel[name].values()) == 9
    schedule = design["pilot_schedule"]
    assert schedule["bootstrap_boss"]["measured_fits"] == 9 * 30 == 270
    assert schedule["semantic_api"]["planned_logical_calls"] == 6 * 3 * 6 == 108


def test_full_projection_and_gate_are_internally_consistent():
    design = _json("data/manifests/p1_v3_runtime_cost_pilot_design.json")
    full = design["full_study_projection"]
    assert full["bootstrap_boss_fits"] == 840 * 200 == 168000
    assert full["semantic_logical_calls"] == 840 * 3 * 6 == 15120
    gate = design["feasibility_gates"]["bootstrap_boss"]
    assert gate["minimum_successful_measured_fits"] >= math.ceil(270 * (1 - gate["maximum_failure_rate"]))
    assert design["feasibility_gates"]["gate_policy"] == "all_must_pass"


def test_offline_boundary_and_scientific_separation():
    design = _json("data/manifests/p1_v3_runtime_cost_pilot_design.json")
    boundary = design["evidence_boundary"]
    assert boundary["synthetic_pilot_scenes_materialized"] == 0
    assert boundary["observation_rows_generated"] == 0
    assert boundary["bootstrap_or_boss_runs"] == 0
    assert boundary["semantic_api_calls"] == 0
    assert boundary["real_successor_scenes_generated"] == 0
    assert boundary["historical_cohorts_accessed"] is False
    assert boundary["final_holdout_accessed"] is False
    result_boundary = design["result_boundary"]
    assert result_boundary["pilot_results_cannot_change_scientific_thresholds"] is True
    assert result_boundary["pilot_scenes_cannot_enter_development_calibration_validation_or_holdout"] is True


def test_pricing_is_deferred_to_hash_pinned_preflight():
    design = _json("data/manifests/p1_v3_runtime_cost_pilot_design.json")
    cost = design["cost_accounting"]
    assert cost["pricing_not_frozen_in_offline_design"] is True
    required = cost["execution_requires_rate_card"]
    assert required["captured_at_utc"] == "required"
    assert required["rate_card_sha256"] == "required"
    assert cost["pilot_hard_cost_cap_usd"] == 1.5


def test_audit_hashes_and_authorization_fail_closed():
    audit = _json("data/manifests/p1_v3_runtime_cost_pilot_design_audit.json")
    for row in audit["dependencies"] + audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])
    assert audit["implementation"]["sha256"] == _hash(audit["implementation"]["path"])
    assert audit["verdict"]["offline_design_frozen"] is True
    assert audit["verdict"]["pilot_execution_authorized"] is False
    authorization = audit["authorization"]
    assert authorization["next_action"] == "P1_V3_RUNTIME_COST_PILOT_PREFLIGHT_FREEZE"
    assert authorization["preflight_freeze_offline"] is True
    assert all(
        authorization[key] is False
        for key in (
            "pilot_execution", "successor_cohort_generation", "study_scene_bootstrap_execution",
            "semantic_api_calls", "final_holdout_access",
        )
    )


def test_config_remains_design_only():
    config = yaml.safe_load((ROOT / "configs/p1_v3_runtime_cost_pilot_design.yaml").read_text(encoding="utf-8"))
    assert config["status"] == "design_frozen_execution_forbidden"
    assert config["purpose"]["scientific_hypothesis_test"] is False
    assert config["synthetic_panel"]["scene_ids_materialized_now"] is False
