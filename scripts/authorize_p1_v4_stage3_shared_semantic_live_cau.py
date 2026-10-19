"""Record explicit user authorization for the already-frozen P1V4 semantic plan."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_live_authorization_checkpoint_cau.json"
CHECKPOINT_AUDIT = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_live_authorization_audit_cau.json"
PLAN = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_plan_cau.json"
OUT = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_live_execution_authorization_cau.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write(value: object) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())


def main() -> int:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    audit = json.loads(CHECKPOINT_AUDIT.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_READY_FOR_EXPLICIT_LIVE_AUTHORIZATION" or audit.get("status") != checkpoint.get("status"):
        raise RuntimeError("authorization checkpoint not ready")
    if len(plan.get("logical_calls", [])) != 360 or audit.get("logical_calls") != 360:
        raise RuntimeError("frozen workload is not exactly 360")
    write({"schema_version": "fourgraph.p1_v4_shared_semantic_live_execution_authorization.v1",
           "task": "P1_V4_STAGE_3D_SHARED_SEMANTIC_LIVE_EXECUTION",
           "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True,
           "checkpoint_sha256": sha(CHECKPOINT), "checkpoint_audit_sha256": sha(CHECKPOINT_AUDIT),
           "execution_plan_sha256": sha(PLAN), "authorized_logical_calls": 360,
           "authorization_scope": "exact_frozen_plan_only", "transport_retry": "not_authorized",
           "oracle_access": False, "holdout_access": False, "downstream_reasoner": False})
    print(json.dumps(json.loads(OUT.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
