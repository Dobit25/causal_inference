from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_c_is_fail_closed_without_live_tools() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    subprocess.run(
        [sys.executable, "scripts/verify_p1v3_statistical_ensemble_phase_c.py"],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    audit = json.loads((ROOT / "data/manifests/p1v3_statistical_ensemble_phase_c_verification_audit.json").read_text())
    assert audit["evidence_boundary"]["statistical_fits"] == 0
    assert audit["evidence_boundary"]["semantic_api_calls"] == 0
    assert audit["phase_d_authorized"] is False

