"""Record explicit user authorization for the separately frozen look-120 Oracle scorer.

No Oracle, SCM, statistical, or semantic artifact is read by this authorization step.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_oracle_scoring_authorization.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"non-deterministic artifact drift: {path}")
        return
    path.write_bytes(payload)


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checkpoint_path = ROOT / cfg["parent_checkpoint"]["path"]
    checkpoint_audit_path = ROOT / cfg["parent_checkpoint_audit"]["path"]
    if sha(checkpoint_path) != cfg["parent_checkpoint"]["sha256"]:
        raise RuntimeError("Oracle-scoring checkpoint hash drift")
    if sha(checkpoint_audit_path) != cfg["parent_checkpoint_audit"]["sha256"]:
        raise RuntimeError("Oracle-scoring checkpoint audit hash drift")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint_audit = json.loads(checkpoint_audit_path.read_text(encoding="utf-8"))
    required = "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION"
    if checkpoint.get("status") != required or checkpoint_audit.get("status") != required:
        raise RuntimeError("parent Oracle-scoring checkpoint is not ready")
    verification = checkpoint.get("verification", {})
    if any(verification.get(key) != 0 for key in ("oracle_access", "holdout_access", "semantic_api_calls", "metrics_calculated", "closure")):
        raise RuntimeError("checkpoint boundary evidence is not clean")
    if verification.get("exact_calibration_scenes", checkpoint_audit.get("exact_calibration_scenes")) not in (None, 120):
        raise RuntimeError("unexpected scene scope")

    authorization = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_oracle_scoring_authorization.v1",
        "task": cfg["task"],
        "status": "AUTHORIZED_CALIBRATION_DEVELOPMENT_ORACLE_SCORING_EXECUTION",
        "config_sha256": sha(CONFIG),
        "checkpoint_sha256": sha(checkpoint_path),
        "checkpoint_audit_sha256": sha(checkpoint_audit_path),
        "explicit_user_authorization": True,
        "scope": cfg["scope"],
        "authorized_calculations": cfg["authorized_calculations"],
        "boundaries": cfg["boundaries"],
    }
    output = ROOT / cfg["outputs"]["authorization"]
    write_once(output, canonical(authorization))
    audit = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_oracle_scoring_authorization_audit.v1",
        "task": cfg["task"],
        "status": authorization["status"],
        "authorization_sha256": sha(output),
        "checkpoint_hash_matches": True,
        "checkpoint_audit_hash_matches": True,
        "authorized_scene_count": 120,
        "oracle_access_during_authorization": 0,
        "holdout_access": 0,
        "semantic_api_calls": 0,
        "metrics_calculated": 0,
        "closure": 0,
    }
    write_once(ROOT / cfg["outputs"]["audit"], canonical(audit))
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
