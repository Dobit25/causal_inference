import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

def test_look400_execution_and_rescore_are_complete():
    stat = load("data/manifests/p1_v4_look400_incremental_statistical_execution_audit.json")
    semantic = load("data/manifests/p1_v4_look400_incremental_mini_semantic_execution_audit.json")
    rescore = load("data/manifests/p1_v4_look400_incremental_response_freeze_rescore_audit.json")
    assert stat["status"] == "PASS_STATISTICAL_EXECUTION"
    assert stat["complete_terminal_records"] == stat["planned_fits"] == 8240
    assert semantic["status"] == "PASS"
    assert semantic["recorded_logical_calls"] == semantic["planned_logical_calls"] == 480
    assert rescore["status"] == "PASS"
    assert rescore["pair_records"] == 3204
    assert rescore["six_vote_groups"] == 534
    assert rescore["production_reference_disagreements"] == 0

def test_look400_oracle_scope_and_registered_decision():
    audit = load("data/manifests/p1_v4_look400_cumulative_overlay_oracle_metric_audit.json")
    result = load("data/manifests/p1_v4_look400_cumulative_overlay_oracle_metric_results.json")
    review = load("data/manifests/p1_v4_look400_overlay_result_review_and_look440_go_no_go.json")
    assert audit["status"] == "PASS_ORACLE_SCORING"
    assert audit["oracle_scenes_accessed"] == 400
    assert audit["validation_access"] == audit["holdout_access"] == 0
    assert result["status"] == "CONTINUE_TO_LOOK_440"
    assert review["status"] == "PASS_REVIEWED"
    assert review["decision"] == "CONTINUE_TO_LOOK_440"
    assert review["next_registered_look"] == 440
