import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION = ROOT / "data/manifests/p1_v4_look120_overlay_result_review_and_look160_go_no_go.json"
AUDIT = ROOT / "data/manifests/p1_v4_look120_overlay_result_review_and_look160_go_no_go_audit.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_decision_continues_to_registered_look160_without_live_authorization():
    item = load(DECISION)
    assert item["status"] == "PASS_OFFLINE_LOOK120_REVIEW"
    assert item["decision"] == "CONTINUE_TO_REGISTERED_LOOK_160"
    assert item["scope"]["registered_look"] == 120
    assert item["scope"]["next_registered_look"] == 160
    assert item["scope"]["incremental_scenes_if_later_authorized"] == 40
    assert item["live_look160_execution_authorized"] is False
    assert item["automatic_follow_on"] is False


def test_gate_interpretation_is_frozen_without_tuning():
    item = load(DECISION)
    interpretation = item["scientific_interpretation"]
    assert interpretation == {
        "coverage_gate": "PASS",
        "ambiguous_abstention_gate": "PASS",
        "precision_confidence_sequence": "INSUFFICIENT_EVIDENCE_AT_LOOK120",
        "high_guardrail": "INSUFFICIENT_CONTRIBUTING_SCENES_AT_LOOK120",
        "futility": "NOT_TRIGGERED",
        "early_certification": False,
    }
    assert item["policy_changes_authorized"] is False
    assert "threshold_tuning" in item["forbidden_actions"]
    assert "model_or_reasoning_effort_change" in item["forbidden_actions"]


def test_primary_metrics_and_ambiguous_diagnostic_match_frozen_results():
    item = load(DECISION)["primary_results"]
    full = item["variants"]["full"]
    partial = item["variants"]["partial"]
    assert full["combined_published"]["correct"] == 654
    assert full["combined_published"]["published"] == 654
    assert full["coverage"]["crosses"] is True
    assert full["precision_evidence"]["crosses"] is False
    assert full["high_guardrail"]["contributing_scenes"] == 32
    assert partial["combined_published"]["correct"] == 395
    assert partial["combined_published"]["published"] == 395
    assert partial["coverage"]["crosses"] is True
    assert partial["precision_evidence"]["crosses"] is False
    assert partial["high_guardrail"]["contributing_scenes"] == 15
    ambiguous = item["ambiguous_abstention_diagnostic"]
    assert ambiguous["automatic_direction_scenes"] == 0
    assert ambiguous["pass"] is True


def test_old_scorer_is_preserved_only_as_incident_evidence():
    incident = load(DECISION)["incident_evidence"]
    assert incident["classification"] == "SUPERSEDED_INCORRECT_CPDAG_VALIDATOR_FOR_PUBLICATION_OVERLAY"
    assert incident["scientific_use"] == "forbidden"
    assert incident["retention"] == "preserved_as_incident_evidence"
    assert len(incident["artifacts"]) == 6


def test_audit_passes_with_zero_live_side_effects():
    audit = load(AUDIT)
    assert audit["status"] == "PASS_OFFLINE_LOOK120_REVIEW_AND_GO_LOOK160_PLANNING_ONLY"
    assert all(audit["checks"].values())
    assert all(all(checks.values()) for checks in audit["variant_checks"].values())
    assert audit["verdict"]["look160_incremental_plan_freeze_permitted"] is True
    assert audit["verdict"]["look160_materialization_authorized"] is False
    assert audit["verdict"]["look160_semantic_api_authorized"] is False
    assert audit["evidence_boundary"]["semantic_api_calls"] == 0
    assert audit["evidence_boundary"]["statistical_fits"] == 0
    assert audit["evidence_boundary"]["oracle_reads"] == 0
    assert audit["evidence_boundary"]["holdout_access"] is False


def test_checkpoint_replays_byte_exact():
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/freeze_p1_v4_look120_overlay_result_review_and_look160_go_no_go.py",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "replays byte-for-byte" in completed.stdout
