import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_is_exactly_30_and_live_closed() -> None:
    audit = json.loads((ROOT / "data/manifests/p1_v4_stage3_method_development_preflight_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS_STAGE_3D_PREFLIGHT_FREEZE"
    assert all(audit["checks"].values())
    assert audit["counts"] == {"development_scenes": 30, "statistical_fits": 6180, "semantic_logical_calls": 360, "historical_reference_tokens": 651903}
    assert audit["execution_boundary"]["scenes_materialized"] == 0
    assert audit["execution_boundary"]["semantic_api_calls"] == 0


def test_preflight_replays_exactly() -> None:
    run = subprocess.run([sys.executable, "scripts/freeze_p1_v4_stage3_method_development_preflight.py", "--check"], cwd=ROOT, text=True, capture_output=True)
    assert run.returncode == 0, run.stdout + run.stderr
