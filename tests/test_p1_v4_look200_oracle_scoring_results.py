import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_look200_oracle_audit_and_replay_hashes() -> None:
    audit = json.loads(
        (ROOT / "data/manifests/p1_v4_look200_cumulative_overlay_oracle_metric_audit.json").read_text()
    )
    dataset = ROOT / "data/manifests/p1_v4_look200_cumulative_overlay_oracle_metric_dataset.jsonl"
    overlays = ROOT / "data/manifests/p1_v4_look200_cumulative_overlay_outputs.jsonl"
    assert audit["status"] == "PASS_ORACLE_SCORING"
    assert audit["oracle_scenes_accessed"] == 200
    assert audit["oracle_commitments_verified"] == 200
    assert audit["metric_dataset_sha256"] == digest(dataset)
    assert audit["overlay_outputs_sha256"] == digest(overlays)
    assert audit["semantic_api_calls"] == 0
    assert audit["statistical_reruns"] == 0
    assert audit["validation_access"] == 0
    assert audit["holdout_access"] == 0


def test_look200_registered_decision_is_continue() -> None:
    results = json.loads(
        (ROOT / "data/manifests/p1_v4_look200_cumulative_overlay_oracle_metric_results.json").read_text()
    )
    primary = results["conditions"]["Constrained-BOSS"]
    assert results["status"] == "CONTINUE_TO_LOOK_240"
    assert primary["variants"]["full"]["registered_gate_pass"] is True
    assert primary["variants"]["partial"]["precision_confidence_sequence"]["pass"] is True
    assert primary["variants"]["partial"]["coverage"]["crosses"] is True
    assert primary["variants"]["partial"]["High_guardrail"]["contributing_scenes"] == 22
    assert primary["variants"]["partial"]["High_guardrail"]["pass"] is False
    assert primary["ambiguous_abstention_diagnostic"]["pass"] is True
    assert not any(row["futile"] for row in results["futility"].values())


def test_look200_review_does_not_authorize_look240_or_validation() -> None:
    review_path = ROOT / "data/manifests/p1_v4_look200_result_review_and_look240_go_no_go.json"
    review = json.loads(review_path.read_text())
    audit = json.loads(
        (ROOT / "data/manifests/p1_v4_look200_result_review_and_look240_go_no_go_audit.json").read_text()
    )
    assert review["decision"] == "CONTINUE_TO_REGISTERED_LOOK_240"
    assert review["policy_change"] is False
    assert review["look240_execution_authorized"] is False
    assert review["validation_authorized"] is False
    assert review["holdout_access"] == 0
    assert audit["status"] == "PASS"
    assert audit["review_sha256"] == digest(review_path)
