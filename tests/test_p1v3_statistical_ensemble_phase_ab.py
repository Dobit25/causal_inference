from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "scripts/build_p1v3_statistical_ensemble_phase_ab.py", *args],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_phase_ab_build_and_replay() -> None:
    built = json.loads(run().stdout)
    assert built["status"].startswith("PASS_OFFLINE")
    replay = json.loads(run("--check").stdout)
    assert replay["status"] == "PASS_REPLAY"


def test_no_live_evidence_boundary() -> None:
    audit = json.loads(
        (ROOT / "data/manifests/p1v3_statistical_ensemble_phase_ab_audit.json").read_text()
    )
    assert audit["evidence_boundary"] == {
        "study_scene_materialization": 0,
        "observations_loaded": False,
        "statistical_fits": 0,
        "semantic_api_calls": 0,
        "oracle_accessed": False,
        "holdout_accessed": False,
    }

