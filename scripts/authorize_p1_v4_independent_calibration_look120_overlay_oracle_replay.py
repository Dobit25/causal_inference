"""Authorize one offline Oracle replay under the frozen evidence-overlay contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_overlay_oracle_replay_authorization.yaml"


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
    for name, parent in cfg["parents"].items():
        path = ROOT / parent["path"]
        if not path.is_file() or sha(path) != parent["sha256"]:
            raise RuntimeError(f"pinned parent hash drift: {name}")
    checkpoint = json.loads((ROOT / cfg["parents"]["original_oracle_scoring_checkpoint"]["path"]).read_text(encoding="utf-8"))
    amendment = json.loads((ROOT / cfg["parents"]["evidence_annotated_overlay_amendment"]["path"]).read_text(encoding="utf-8"))
    amendment_audit = json.loads((ROOT / cfg["parents"]["evidence_annotated_overlay_audit"]["path"]).read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION":
        raise RuntimeError("original checkpoint is not eligible")
    if amendment.get("status") != "PASS_OFFLINE_FROZEN" or amendment_audit.get("status") != "PASS":
        raise RuntimeError("evidence-annotated overlay amendment did not pass")
    if amendment_audit.get("metric_recalculation") != 0 or amendment_audit.get("oracle_access") != 0:
        raise RuntimeError("amendment was not an offline-only freeze")
    scene_ids = checkpoint["scope"]["exact_scene_ids"]
    if len(scene_ids) != 120 or len(set(scene_ids)) != 120:
        raise RuntimeError("exact calibration scope drift")
    authorization = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_overlay_oracle_replay_authorization.v1",
        "task": cfg["task"],
        "status": "AUTHORIZED_CALIBRATION_DEVELOPMENT_OVERLAY_ORACLE_REPLAY",
        "config_sha256": sha(CONFIG),
        "explicit_user_authorization": True,
        "parents": cfg["parents"],
        "scope": {**cfg["scope"], "exact_scene_ids": scene_ids},
        "authorized_calculations": cfg["authorized_calculations"],
        "boundaries": cfg["boundaries"],
    }
    authorization_path = ROOT / cfg["outputs"]["authorization"]
    write_once(authorization_path, canonical(authorization))
    audit = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_overlay_oracle_replay_authorization_audit.v1",
        "task": cfg["task"],
        "status": authorization["status"],
        "authorization_sha256": sha(authorization_path),
        "all_parent_hashes_match": True,
        "authorized_scene_count": len(scene_ids),
        "oracle_access_during_authorization": 0,
        "holdout_access": 0,
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "metric_recalculation": 0,
        "meek_closure": 0,
    }
    write_once(ROOT / cfg["outputs"]["audit"], canonical(audit))
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
