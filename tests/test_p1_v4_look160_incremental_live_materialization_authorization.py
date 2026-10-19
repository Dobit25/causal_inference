import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "data/manifests/p1_v4_look160_incremental_live_materialization_authorization.json"
AUDIT = ROOT / "data/manifests/p1_v4_look160_incremental_live_materialization_authorization_audit.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_authorization_is_exact_and_materialization_only():
    item = load(AUTH)
    scope = item["authorization"]
    assert item["status"] == "PASS_SCOPED_LOOK160_INCREMENTAL_MATERIALIZATION_AUTHORIZATION"
    assert scope["materialization_authorized"] is True
    assert scope["scene_count"] == len(scope["exact_scene_ids"]) == 40
    assert scope["public_story_artifact_count"] == 120
    assert scope["story_variants"] == ["full", "partial", "ambiguous"]
    forbidden = [key for key in scope if key.endswith("_authorized") and key != "materialization_authorized"]
    assert all(scope[key] is False for key in forbidden)


def test_checkpoint_itself_has_zero_side_effects():
    item = load(AUTH)
    assert all(value in (0, False) for value in item["side_effects_at_checkpoint"].values())
    audit = load(AUDIT)
    assert audit["status"] == "PASS_SCOPED_AUTHORIZATION"
    assert audit["counts"]["materialized_at_checkpoint"] == 0
    assert audit["counts"]["semantic_api_calls"] == 0
    assert audit["counts"]["oracle_reads"] == 0


def test_all_authorization_checks_pass():
    assert all(load(AUDIT)["checks"].values())


def test_authorization_replays_before_execution_or_remains_preserved_after_execution():
    if (ROOT / "data/manifests/p1_v4_independent_calibration_look160_incremental_materialization.json").exists():
        assert load(AUTH)["status"] == "PASS_SCOPED_LOOK160_INCREMENTAL_MATERIALIZATION_AUTHORIZATION"
        assert load(AUDIT)["status"] == "PASS_SCOPED_AUTHORIZATION"
        return
    completed = subprocess.run(
        [sys.executable, "scripts/freeze_p1_v4_look160_incremental_live_materialization_authorization.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"check": true' in completed.stdout.lower()
