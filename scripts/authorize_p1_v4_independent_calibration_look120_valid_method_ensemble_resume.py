"""Record explicit authorization for the exact missing statistical identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_authorization_checkpoint.json"
RESUME_PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_plan.json"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_statistical.py"
OUT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_live_authorization.json"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    plan = json.loads(RESUME_PLAN.read_text(encoding="utf-8"))
    if checkpoint["status"] != "READY_FOR_EXPLICIT_LIVE_AUTHORIZATION": raise SystemExit("resume checkpoint is not ready")
    if len(plan["jobs"]) != 22683: raise SystemExit("resume plan identity count mismatch")
    payload = {
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_VALID_METHOD_ENSEMBLE_RESUME_LIVE_AUTHORIZATION",
        "status": "PASS_VALID_METHOD_ENSEMBLE_RESUME_AUTHORIZATION",
        "explicit_user_live_authorization_recorded": True,
        "exact_missing_execution_identities": len(plan["jobs"]),
        "cached_terminal_execution_identities_not_rerun": plan["terminal_cached_execution_identities"],
        "concurrency": 1,
        "automatic_retry": False,
        "boundary": {"semantic_api_calls": False, "oracle_access": False, "holdout_access": False, "parameter_changes": False},
        "dependencies": {"checkpoint_sha256": sha(CHECKPOINT), "resume_plan_sha256": sha(RESUME_PLAN), "runner_sha256": sha(RUNNER)},
    }
    data = canonical(payload); OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and OUT.read_bytes() != data: raise SystemExit("live authorization drift")
    if not OUT.exists(): OUT.write_bytes(data)
    print(json.dumps({"status": payload["status"], "exact_missing_execution_identities": len(plan["jobs"])}))


if __name__ == "__main__": main()
