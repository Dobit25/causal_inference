import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_look240_review_requires_registered_look280():
    review = load("data/manifests/p1_v4_look240_result_review_and_look280_go_no_go.json")
    audit = load("data/manifests/p1_v4_look240_result_review_and_look280_go_no_go_audit.json")
    assert review["status"] == "PASS_OFFLINE_REVIEW"
    assert review["decision"] == "CONTINUE_TO_REGISTERED_LOOK_280"
    assert review["primary_summary"]["full"]["registered_gate_pass"] is True
    assert review["primary_summary"]["partial"]["registered_gate_pass"] is False
    assert review["primary_summary"]["partial"]["High_guardrail"]["contributing_scenes"] == 26
    assert audit["status"] == "PASS"
    assert audit["validation_access"] == audit["holdout_access"] == 0


def test_look280_increment_is_exact_and_unexecuted():
    plan = load("data/manifests/p1_v4_look280_incremental_exact_identity_plan.json")
    audit = load("data/manifests/p1_v4_look280_incremental_exact_identity_audit.json")
    ids = plan["incremental_scene_ids_in_execution_order"]
    assert plan["status"] == "PASS_FROZEN_EXACT_40_IDENTITIES_OFFLINE"
    assert len(ids) == len(set(ids)) == 40
    assert plan["previous_registered_look"] == 240
    assert plan["next_registered_look"] == 280
    assert len(plan["cumulative_scene_ids_in_execution_order"]) == 280
    assert set(ids).isdisjoint(plan["cumulative_scene_ids_in_execution_order"][:240])
    assert plan["authorization"]["identity_freeze_complete"] is True
    assert all(
        value is False
        for key, value in plan["authorization"].items()
        if key != "identity_freeze_complete"
    )
    assert audit["counts"]["semantic_api_calls"] == 0
    assert audit["counts"]["oracle_reads"] == 0


def test_byte_for_byte_replay():
    result = subprocess.run(
        [sys.executable, "scripts/freeze_p1_v4_look240_review_and_look280_identities.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
