"""Freeze a no-access checkpoint for later explicit development-Oracle scoring."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_paired_oracle_scoring_authorization_checkpoint.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def group_ids(path: Path) -> set[tuple[str, str, str]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(row["scene_id"], row["variant"], row["pair_id"]) for row in rows}


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for parent in cfg["parents"].values():
        if sha(ROOT / parent["path"]) != parent["sha256"]:
            raise RuntimeError(f"parent hash drift: {parent['path']}")
    review = json.loads((ROOT / cfg["parents"]["offline_review"]["path"]).read_text(encoding="utf-8"))
    audit = json.loads((ROOT / cfg["parents"]["offline_review_audit"]["path"]).read_text(encoding="utf-8"))
    if review.get("status") != "PASS_REVIEW_COMPLETE" or audit.get("status") != "PASS":
        raise RuntimeError("offline review has not passed")
    nano_ids = group_ids(ROOT / cfg["parents"]["nano_six_vote_groups"]["path"])
    mini_ids = group_ids(ROOT / cfg["parents"]["mini_six_vote_groups"]["path"])
    allowed = {f"P1V4SD{i:03d}" for i in range(30)}
    seen = {scene for scene, _, _ in nano_ids}
    if nano_ids != mini_ids or len(nano_ids) != cfg["scope"]["expected_six_vote_groups_per_model"] or seen != allowed:
        raise RuntimeError("frozen scoring groups do not match the exact development cohort")
    checkpoint = {"schema_version": "fourgraph.p1_v4_stage3_paired_oracle_scoring_authorization_checkpoint.v1", "task": cfg["task"],
                  "status": "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION", "config_sha256": sha(CONFIG), "parents": cfg["parents"],
                  "scope": cfg["scope"], "registered_metrics_after_explicit_authorization": cfg["registered_metrics_after_explicit_authorization"],
                  "forbidden_before_oracle_scoring": cfg["forbidden_before_oracle_scoring"], "authorization_boundary": cfg["authorization_boundary"],
                  "verification": {"same_frozen_group_identities": True, "group_count_per_model": len(nano_ids), "scene_count": len(seen), "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0, "closure": 0}}
    out = ROOT / cfg["outputs"]["checkpoint"]; out.write_bytes(canonical(checkpoint))
    final_audit = {"schema_version": "fourgraph.p1_v4_stage3_paired_oracle_scoring_authorization_checkpoint_audit.v1", "task": cfg["task"], "status": checkpoint["status"],
                   "checkpoint_sha256": sha(out), "all_parent_hashes_match": True, "exact_development_scenes": 30, "same_groups_for_both_models": True,
                   "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0, "metrics_calculated": 0, "closure": 0}
    audit_path = ROOT / cfg["outputs"]["audit"]; audit_path.write_bytes(canonical(final_audit))
    report = """# P1V4 paired Oracle-scoring authorization checkpoint\n\nThe paired Nano-medium/Mini-medium response review passed. This checkpoint freezes the exact 30-development-scene group identities, model policy, and scoring definitions for a later, separately authorized development-Oracle operation.\n\nNo Oracle or holdout data were accessed here. It does not select a model, tune a threshold, calculate metrics, or run closure.\n"""
    (ROOT / cfg["outputs"]["report"]).write_text(report, encoding="utf-8")
    print(json.dumps(final_audit, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
