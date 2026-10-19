"""Record explicit authorization to score only the frozen P1V4 development groups."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "data/manifests/p1_v4_stage3_paired_oracle_scoring_authorization_checkpoint.json"
AUDIT = ROOT / "data/manifests/p1_v4_stage3_paired_oracle_scoring_authorization_checkpoint_audit.json"
OUT = ROOT / "data/manifests/p1_v4_stage3_paired_oracle_scoring_authorization.json"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    checkpoint, audit = json.loads(CHECKPOINT.read_text(encoding="utf-8")), json.loads(AUDIT.read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION" or audit.get("status") != checkpoint.get("status"):
        raise RuntimeError("Oracle scoring checkpoint is not ready")
    value = {"schema_version": "fourgraph.p1_v4_stage3_paired_oracle_scoring_authorization.v1", "task": "P1_V4_STAGE_3D_PAIRED_ORACLE_SCORING_EXECUTION",
             "status": "ELIGIBLE_WAITING_FOR_ORACLE_SCORING_EXECUTION", "explicit_user_oracle_scoring_authorization": True,
             "checkpoint_sha256": sha(CHECKPOINT), "checkpoint_audit_sha256": sha(AUDIT), "authorized_scene_ids": [f"P1V4SD{i:03d}" for i in range(30)],
             "models": ["nano_medium", "mini_medium"], "oracle_cohort": "development_only", "closure": False, "semantic_api_calls": 0, "holdout_access": False}
    OUT.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")); print(json.dumps(value, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
