import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look160_incremental_exact_identity_plan.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look160_incremental_exact_identity_audit.json"
ROWS = ROOT / "data/manifests/p1_v4_independent_calibration_look160_incremental_exact_identities.jsonl"
PARENT_PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_exact_identity_plan.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_exact_registered_40_scene_slice_is_frozen():
    plan = load(PLAN)
    parent = load(PARENT_PLAN)
    assert plan["status"] == "PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE"
    assert plan["incremental_scene_count"] == 40
    assert plan["cumulative_scene_count"] == 160
    assert plan["incremental_scene_ids_in_execution_order"] == parent["exact_scene_ids_in_execution_order"][120:160]
    assert plan["cumulative_scene_ids_in_execution_order"] == parent["exact_scene_ids_in_execution_order"][:160]


def test_rows_preserve_registered_ids_seeds_and_batch():
    rows = load_rows(ROWS)
    assert len(rows) == 40
    assert len({row["study_id"] for row in rows}) == 40
    assert {row["batch_id"] for row in rows} == {"semantic_calibration:120-160"}
    assert {row["first_registered_look"] for row in rows} == {160}
    assert all(row["scene_materialized"] is False for row in rows)
    assert all(row["diagnostic_memberships"] == [] for row in rows)
    assert all(len(row["component_seeds"]) == 6 for row in rows)


def test_audit_is_offline_and_requires_new_authorization():
    audit = load(AUDIT)
    assert audit["status"] == "PASS_OFFLINE_EXACT_IDENTITY_FREEZE"
    assert all(audit["checks"].values())
    assert audit["counts"]["new_scenes_materialized"] == 0
    assert audit["counts"]["statistical_fits"] == 0
    assert audit["counts"]["semantic_api_calls"] == 0
    assert audit["counts"]["oracle_reads"] == 0
    assert audit["execution_boundary"]["live_execution_authorized"] is False


def test_node_strata_remain_balanced_in_increment():
    assert load(AUDIT)["node_count_distribution"] == {"5": 13, "6": 13, "7": 14}


def test_checkpoint_replays_before_execution_or_remains_preserved_after_execution():
    if (ROOT / "data/manifests/p1_v4_independent_calibration_look160_incremental_materialization.json").exists():
        assert load(PLAN)["status"] == "PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE"
        assert load(AUDIT)["status"] == "PASS_OFFLINE_EXACT_IDENTITY_FREEZE"
        return
    completed = subprocess.run(
        [sys.executable, "scripts/freeze_p1_v4_independent_calibration_look160_incremental_identities.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"check": true' in completed.stdout.lower()
