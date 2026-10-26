import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_exactly_one_transport_retry_resolved_the_only_incident():
    audit = load("data/manifests/p1_v4_look320_incremental_mini_transport_retry_audit.json")
    assert audit["status"] == "PASS_RESPONSE_RECEIVED"
    assert audit["logical_id"] == "P1V4SC280/full/P1"
    assert audit["recorded_retries"] == 1


def test_response_rescore_is_complete_and_independent():
    audit = load("data/manifests/p1_v4_look320_incremental_response_freeze_rescore_audit.json")
    assert audit["status"] == "PASS"
    assert audit["effective_logical_responses"] == 480
    assert audit["pair_records"] == 3312
    assert audit["six_vote_groups"] == 552
    assert audit["production_reference_disagreements"] == 0
    assert audit["unresolved_provider_errors"] == 0


def test_oracle_scope_and_registered_decision_are_fail_closed():
    audit = load("data/manifests/p1_v4_look320_cumulative_overlay_oracle_metric_audit.json")
    result = load("data/manifests/p1_v4_look320_cumulative_overlay_oracle_metric_results.json")
    review = load("data/manifests/p1_v4_look320_overlay_result_review_and_look360_go_no_go.json")
    assert audit["status"] == "PASS_ORACLE_SCORING"
    assert audit["oracle_scenes_accessed"] == 320
    assert audit["validation_access"] == audit["holdout_access"] == 0
    assert result["status"] == "CONTINUE_TO_LOOK_360"
    assert not result["futility"]["full"]["futile"]
    assert not result["futility"]["partial"]["futile"]
    assert review["decision"] == "CONTINUE_TO_LOOK_360"
    assert review["policy_changes"] == 0
