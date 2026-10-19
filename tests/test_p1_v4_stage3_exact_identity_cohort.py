import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rows():
    return [json.loads(line) for line in (ROOT / "data/manifests/p1_v4_stage3_exact_identities.jsonl").read_text(encoding="utf-8").splitlines() if line]


def test_fresh_identity_plan_is_complete_and_unmaterialized() -> None:
    values = rows()
    assert len(values) == 950
    assert Counter(row["role"] for row in values) == {"method_development": 30, "semantic_calibration": 440, "threshold_validation": 480}
    assert all(row["study_id"].startswith("P1V4") and row["scene_materialized"] is False for row in values)
    assert len({row["study_id"] for row in values}) == len({row["contract_scene_id"] for row in values}) == 950
    assert len({seed for row in values for seed in row["component_seeds"].values()}) == 5700


def test_identity_hashes_and_replay_are_exact() -> None:
    for row in rows():
        payload = {key: value for key, value in row.items() if key != "identity_sha256"}
        assert row["identity_sha256"] == hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest().upper()
    run = subprocess.run([sys.executable, "scripts/freeze_p1_v4_stage3_exact_identity_cohort.py", "--check"], cwd=ROOT, text=True, capture_output=True)
    assert run.returncode == 0, run.stdout + run.stderr
