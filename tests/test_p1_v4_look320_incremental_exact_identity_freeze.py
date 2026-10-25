import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_look320_increment_is_exact_unique_and_unexecuted():
    plan = load("data/manifests/p1_v4_look320_incremental_exact_identity_plan.json")
    audit = load("data/manifests/p1_v4_look320_incremental_exact_identity_audit.json")
    master = load("data/manifests/p1_v4_independent_calibration_exact_identity_plan.json")
    ids = plan["incremental_scene_ids_in_execution_order"]
    assert plan["status"] == "PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE"
    assert ids == master["exact_scene_ids_in_execution_order"][280:320]
    assert len(ids) == len(set(ids)) == 40
    assert plan["previous_registered_look"] == 280
    assert plan["next_registered_look"] == 320
    assert len(plan["cumulative_scene_ids_in_execution_order"]) == 320
    assert set(ids).isdisjoint(plan["cumulative_scene_ids_in_execution_order"][:280])
    assert plan["authorization"]["identity_freeze_complete"] is True
    assert all(
        value is False
        for key, value in plan["authorization"].items()
        if key != "identity_freeze_complete"
    )
    assert audit["status"] == "PASS"
    assert audit["counts"]["scenes_materialized"] == 0
    assert audit["counts"]["statistical_fits"] == 0
    assert audit["counts"]["semantic_api_calls"] == 0
    assert audit["counts"]["oracle_reads"] == 0
    assert audit["validation_access"] == audit["holdout_access"] == 0


def test_look320_freeze_byte_for_byte_replay():
    result = subprocess.run(
        [sys.executable, "scripts/freeze_p1_v4_look320_incremental_exact_identities.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
