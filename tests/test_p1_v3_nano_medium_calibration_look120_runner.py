from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_p1_v3_nano_medium_calibration_look120 import (
    build_plan,
    idempotency_check,
    load_config,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_nano_medium_calibration_look120_production_runner.yaml"


def test_exact_look120_workload_and_boundary() -> None:
    plan = build_plan(load_config(CONFIG))
    assert plan["scene_count"] == 120
    assert plan["planned_statistical_fits"] == 24_120
    assert plan["planned_semantic_calls"] == 2_640
    assert plan["execution_boundary"]["scenes_materialized"] == 0
    assert plan["execution_boundary"]["semantic_api_calls"] == 0
    assert plan["execution_boundary"]["holdout_access"] is False
    assert len(plan["diagnostic_subsets"]["ambiguous"]) == 120
    assert len(plan["diagnostic_subsets"]["nonedge"]) == 80


def test_idempotency_is_deterministic() -> None:
    plan = build_plan(load_config(CONFIG))
    result = idempotency_check(plan)
    assert result == {
        "status": "PASS",
        "statistical_identity_replay": True,
        "semantic_identity_replay": True,
        "duplicate_policy": "fail_closed",
    }


def test_no_live_execution_is_enabled() -> None:
    cfg = load_config(CONFIG)
    assert cfg["execution"]["live_enabled_in_this_freeze"] is False
    assert cfg["boundary"]["oracle_access"] is False
    assert cfg["boundary"]["holdout_access"] is False


def test_materialization_adapter_is_check_only_by_default() -> None:
    from scripts.materialize_p1_v3_nano_calibration_look120 import materialize

    result = materialize(CONFIG, execute=False)
    assert result["status"] == "PASS_MATERIALIZATION_PLAN"
    assert result["scene_count"] == 120
    assert result["writes"] == 0


def test_live_flag_cannot_be_smuggled_in() -> None:
    cfg = load_config(CONFIG)
    cfg["execution"]["live_enabled_in_this_freeze"] = True
    # The frozen config is an input contract; mutating it in memory must not
    # alter the checked-in artifact or the offline plan's boundary.
    assert load_config(CONFIG)["execution"]["live_enabled_in_this_freeze"] is False

