"""Record the user's explicit, development-only Oracle authorization."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_parent_semantic_metric_oracle_authorization.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for key in ("parent_checkpoint", "parent_checkpoint_audit"):
        item = cfg[key]
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"frozen dependency drift: {item['path']}")
    checkpoint = json.loads((ROOT / cfg["parent_checkpoint"]["path"]).read_text(encoding="utf-8"))
    audit = json.loads((ROOT / cfg["parent_checkpoint_audit"]["path"]).read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_READY_FOR_EXPLICIT_PARENT_SEMANTIC_METRIC_AUTHORIZATION" or audit.get("status") != checkpoint.get("status"):
        raise RuntimeError("parent/semantic metric checkpoint is not ready")
    value = {
        "schema_version": "fourgraph.p1_v4_stage3_parent_semantic_metric_oracle_authorization.v1",
        "task": cfg["task"],
        "status": "AUTHORIZED_DEVELOPMENT_ORACLE_METRIC_EXECUTION",
        "explicit_user_authorization": True,
        "config_sha256": sha(CONFIG),
        "checkpoint_sha256": sha(ROOT / cfg["parent_checkpoint"]["path"]),
        "checkpoint_audit_sha256": sha(ROOT / cfg["parent_checkpoint_audit"]["path"]),
        "scope": cfg["scope"],
        "boundaries": cfg["boundaries"],
    }
    output = ROOT / cfg["outputs"]["authorization"]
    output.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
