import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_statistical_and_semantic_execution_are_exact_and_complete():
    statistical = load("data/manifests/p1_v4_look360_incremental_statistical_execution_audit.json")
    semantic = load("data/manifests/p1_v4_look360_incremental_mini_semantic_execution_audit.json")
    assert statistical["status"] == "PASS_STATISTICAL_EXECUTION"
    assert statistical["planned_fits"] == statistical["complete_terminal_records"] == 8240
    assert statistical["error_artifacts"] == 0
    assert semantic["status"] == "PASS"
    assert semantic["planned_logical_calls"] == semantic["recorded_logical_calls"] == 480
    assert semantic["oracle_access"] == semantic["holdout_access"] == 0


def test_response_rescore_is_complete_and_independent():
    audit = load("data/manifests/p1_v4_look360_incremental_response_freeze_rescore_audit.json")
    assert audit["status"] == "PASS"
    assert audit["effective_logical_responses"] == 480
    assert audit["pair_records"] == 3120
    assert audit["six_vote_groups"] == 520
    assert audit["production_reference_disagreements"] == 0
    assert audit["oracle_access"] == 0


def test_oracle_scope_and_registered_decision_are_fail_closed():
    audit = load("data/manifests/p1_v4_look360_cumulative_overlay_oracle_metric_audit.json")
    result = load("data/manifests/p1_v4_look360_cumulative_overlay_oracle_metric_results.json")
    review = load("data/manifests/p1_v4_look360_overlay_result_review_and_look400_go_no_go.json")
    assert audit["status"] == "PASS_ORACLE_SCORING"
    assert audit["oracle_scenes_accessed"] == 360
    assert audit["validation_access"] == audit["holdout_access"] == 0
    assert result["status"] == "CONTINUE_TO_LOOK_400"
    assert not result["futility"]["full"]["futile"]
    assert not result["futility"]["partial"]["futile"]
    assert review["decision"] == "CONTINUE_TO_LOOK_400"
    assert review["policy_changes"] == 0
