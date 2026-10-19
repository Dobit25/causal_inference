import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data/manifests/p1_v4_look160_incremental_materialization_preflight_authorization_checkpoint.json"
AUDIT = ROOT / "data/manifests/p1_v4_look160_incremental_materialization_preflight_authorization_checkpoint_audit.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_preflight_has_exact_increment_scope_and_zero_writes():
    item = load(CHECKPOINT)
    assert item["status"] == "PASS_READY_FOR_SEPARATE_LIVE_MATERIALIZATION_AUTHORIZATION"
    assert item["dry_run"]["scene_count"] == 40
    assert item["dry_run"]["story_artifact_count"] == 120
    assert item["dry_run"]["story_variants"] == ["full", "partial", "ambiguous"]
    assert item["dry_run"]["writes_performed"] == 0
    assert item["dry_run"]["semantic_api_calls"] == 0


def test_live_and_scientific_execution_remain_unauthorized():
    authorization = load(CHECKPOINT)["authorization"]
    assert authorization["preflight_pass"] is True
    assert all(value is False for key, value in authorization.items() if key != "preflight_pass")
    assert load(CHECKPOINT)["next_action"] == "P1_V4_LOOK160_INCREMENTAL_LIVE_MATERIALIZATION_AUTHORIZATION_CHECKPOINT"


def test_story_artifact_completeness_does_not_change_diagnostic_membership():
    boundary = load(CHECKPOINT)["diagnostic_boundary"]
    assert boundary["materialize_all_three_story_variants"] is True
    assert boundary["incremental_ambiguous_membership"] == 0
    assert boundary["semantic_call_workload_registered_here"] is False


def test_audit_passes_all_checks_without_side_effects():
    audit = load(AUDIT)
    assert audit["status"] == "PASS_OFFLINE_PREFLIGHT"
    assert all(audit["checks"].values())
    assert audit["counts"] == {"scenes": 40, "story_artifacts": 120, "writes": 0, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_reads": 0}


def test_runner_refuses_execute_without_separate_authorization():
    completed = subprocess.run(
        [sys.executable, "scripts/materialize_p1_v4_look160_increment.py", "--execute"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert completed.returncode != 0
    assert "requires a separate" in completed.stderr


def test_checkpoint_replays_byte_exact():
    completed = subprocess.run(
        [sys.executable, "scripts/freeze_p1_v4_look160_incremental_materialization_preflight.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"check": true' in completed.stdout.lower()
