"""Record the user-authorized, exact 360-call Mini-medium paired run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AMENDMENT = ROOT / "data/manifests/p1_v4_stage3_mini_medium_paired_comparator_amendment.json"
AUDIT = ROOT / "data/manifests/p1_v4_stage3_mini_medium_paired_comparator_audit.json"
PLAN = ROOT / "data/manifests/p1_v4_stage3_mini_medium_paired_execution_plan.json"
PREFLIGHT = ROOT / "data/manifests/p1_v4_stage3_mini_medium_provider_preflight_cau.json"
PREFLIGHT_AUDIT = ROOT / "data/manifests/p1_v4_stage3_mini_medium_provider_preflight_cau_audit.json"
OUT = ROOT / "data/manifests/p1_v4_stage3_mini_medium_paired_live_authorization.json"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8")); audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8")); preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8")); preflight_audit = json.loads(PREFLIGHT_AUDIT.read_text(encoding="utf-8"))
    if amendment.get("status") != "PASS_FROZEN" or audit.get("status") != "PASS": raise RuntimeError("Mini comparator amendment not frozen")
    if len(plan.get("logical_calls", [])) != 360: raise RuntimeError("Mini workload is not exactly 360")
    if preflight.get("status") != "PASS" or preflight_audit.get("status") != "PASS_PROVIDER_PREFLIGHT": raise RuntimeError("Mini provider preflight did not pass")
    value = {"schema_version": "fourgraph.p1_v4_stage3_mini_medium_paired_live_authorization.v1", "task": "P1_V4_STAGE_3D_MINI_MEDIUM_PAIRED_LIVE_EXECUTION",
             "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True, "authorized_logical_calls": 360,
             "amendment_sha256": sha(AMENDMENT), "amendment_audit_sha256": sha(AUDIT), "execution_plan_sha256": sha(PLAN),
             "provider_preflight_sha256": sha(PREFLIGHT), "provider_preflight_audit_sha256": sha(PREFLIGHT_AUDIT),
             "authorization_scope": "exact_frozen_mini_paired_plan_only", "transport_retry": "not_authorized", "oracle_access": False, "holdout_access": False, "closure": False, "metrics": False}
    OUT.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")); print(json.dumps(value, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
