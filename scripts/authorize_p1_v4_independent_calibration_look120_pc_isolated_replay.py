"""Record the user's explicit authorization for the sole forensic PC replay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_authorization.json"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_pc_isolated_replay.py"
OUT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_pc_isolated_replay_live_authorization.json"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if checkpoint["status"] != "READY_FOR_EXPLICIT_LIVE_AUTHORIZATION":
        raise SystemExit("checkpoint is not ready")
    payload = {
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_PC_ISOLATED_REPLAY_LIVE_AUTHORIZATION",
        "status": "PASS_ISOLATED_PC_REPLAY_LIVE_AUTHORIZATION",
        "explicit_user_authorization_recorded": True,
        "authorization": {"exact_statistical_fits": 1, "semantic_api_calls": False, "oracle_access": False, "holdout_access": False, "phase_d_resume": False},
        "dependencies": {"checkpoint_sha256": sha(CHECKPOINT), "runner_sha256": sha(RUNNER)},
    }
    data = canonical(payload)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and OUT.read_bytes() != data:
        raise SystemExit("live authorization drift")
    if not OUT.exists(): OUT.write_bytes(data)
    print(json.dumps({"status": payload["status"], "exact_statistical_fits": 1}))


if __name__ == "__main__":
    main()
