from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_conformance_artifacts_and_offline_boundary() -> None:
    audit = json.loads((ROOT / "data/manifests/p1_v4_evidence_annotated_conformance_audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS_STAGE_3B_CONFORMANCE"
    assert all(audit["checks"].values())
    assert audit["execution_boundary"]["real_cohort_scenes_materialized"] == 0
    assert audit["execution_boundary"]["semantic_api_calls"] == 0
    assert audit["execution_boundary"]["oracle_access"] is False


def test_conformance_replays_byte_for_byte() -> None:
    run = subprocess.run([sys.executable, "scripts/run_p1_v4_evidence_annotated_conformance.py", "--check"], cwd=ROOT, text=True, capture_output=True)
    assert run.returncode == 0, run.stdout + run.stderr
