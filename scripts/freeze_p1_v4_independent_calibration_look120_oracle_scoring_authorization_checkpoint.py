"""Freeze the exact look-120 inputs allowed for a later Oracle-scoring operation.

This checkpoint intentionally never loads an SCM, Oracle DAG, or holdout artifact.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_oracle_scoring_authorization_checkpoint.yaml"
NORMALIZED = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/normalized"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
            raise RuntimeError(f"parent hash drift: {name}: {parent['path']}")

    statistical_audit = json.loads((ROOT / cfg["parents"]["final_statistical_audit"]["path"]).read_text(encoding="utf-8"))
    execution_audit = json.loads((ROOT / cfg["parents"]["semantic_execution_audit"]["path"]).read_text(encoding="utf-8"))
    rescore_audit = json.loads((ROOT / cfg["parents"]["rescore_audit"]["path"]).read_text(encoding="utf-8"))
    response_freeze = json.loads((ROOT / cfg["parents"]["response_freeze"]["path"]).read_text(encoding="utf-8"))
    parent_plan = json.loads((ROOT / cfg["parents"]["statistical_parent_plan"]["path"]).read_text(encoding="utf-8"))

    if statistical_audit.get("status") != "PASS_STATISTICAL_EXECUTION" or statistical_audit.get("complete_fits") != 24720:
        raise RuntimeError("final statistical execution is not a complete PASS")
    if any(statistical_audit.get("execution_boundary", {}).get(key) not in (0, False) for key in ("oracle_access", "holdout_access", "semantic_api_calls")):
        raise RuntimeError("statistical audit boundary drift")
    if execution_audit.get("status") != "PASS" or execution_audit.get("recorded_logical_calls") != 2160:
        raise RuntimeError("semantic execution is not a complete PASS")
    if rescore_audit.get("status") != "PASS" or rescore_audit.get("production_reference_disagreements") != 0:
        raise RuntimeError("response re-score audit did not pass")
    if response_freeze.get("status") != "PASS_FROZEN" or response_freeze.get("oracle_access") != 0:
        raise RuntimeError("response freeze is not sealed before Oracle")

    scene_ids = sorted(set(parent_plan["scene_ids"]))
    if len(scene_ids) != cfg["scope"]["expected_scenes"]:
        raise RuntimeError("statistical parent plan scene cardinality drift")
    parent_jobs = [
        job for job in parent_plan["jobs"]
        if job["algorithm"] in cfg["scope"]["parent_conditions"]
    ]
    expected_parent_jobs = cfg["scope"]["expected_parent_graph_artifacts"]
    if len(parent_jobs) != expected_parent_jobs:
        raise RuntimeError("unexpected constrained-parent job cardinality")
    inventory: list[dict[str, Any]] = []
    for job in sorted(parent_jobs, key=lambda row: (row["scene_id"], row["algorithm"], row["execution_id"])):
        path = NORMALIZED / f"{job['execution_id']}.json"
        if not path.is_file():
            raise RuntimeError(f"missing normalized parent graph: {job['execution_id']}")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "VALID" or record.get("job") != job:
            raise RuntimeError(f"invalid or mismatched parent graph: {job['execution_id']}")
        inventory.append({
            "scene_id": job["scene_id"],
            "condition": job["algorithm"],
            "execution_id": job["execution_id"],
            "normalized_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "normalized_sha256": sha(path),
            "input_sha256": record.get("input_sha256"),
        })

    pair_records = rows(ROOT / cfg["parents"]["pair_rescore"]["path"])
    group_rows = rows(ROOT / cfg["parents"]["six_vote_groups"]["path"])
    if len(pair_records) != cfg["scope"]["expected_pair_records"] or len(group_rows) != cfg["scope"]["expected_six_vote_groups"]:
        raise RuntimeError("frozen pair/group cardinality drift")
    group_scenes = {row["scene_id"] for row in group_rows}
    variants = Counter(row["variant"] for row in group_rows)
    if group_scenes != set(scene_ids) or set(variants) != set(cfg["scope"]["variants"]):
        raise RuntimeError("six-vote groups do not match frozen cohort/variants")
    if any(row.get("prompt_ids") != cfg["semantic_policy"]["prompt_variants"] for row in group_rows):
        raise RuntimeError("six-vote group prompt identities drift")

    checkpoint = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_oracle_scoring_authorization_checkpoint.v1",
        "task": cfg["task"],
        "status": "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION",
        "config_sha256": sha(CONFIG),
        "parents": cfg["parents"],
        "scope": {**cfg["scope"], "exact_scene_ids": scene_ids},
        "semantic_policy": cfg["semantic_policy"],
        "registered_oracle_metrics_after_explicit_authorization": cfg["registered_oracle_metrics_after_explicit_authorization"],
        "forbidden_until_separate_explicit_oracle_scoring_authorization": cfg["forbidden_until_separate_explicit_oracle_scoring_authorization"],
        "constrained_parent_graph_inventory": inventory,
        "verification": {
            "statistical_fits_complete": statistical_audit["complete_fits"],
            "effective_semantic_logical_calls": execution_audit["recorded_logical_calls"],
            "response_freeze_passed": True,
            "production_reference_disagreements": rescore_audit["production_reference_disagreements"],
            "pair_records": len(pair_records),
            "six_vote_groups": len(group_rows),
            "group_counts_by_variant": dict(sorted(variants.items())),
            "constrained_parent_graphs": len(inventory),
            "oracle_access": 0,
            "holdout_access": 0,
            "semantic_api_calls": 0,
            "metrics_calculated": 0,
            "closure": 0,
        },
    }
    checkpoint_path = ROOT / cfg["outputs"]["checkpoint"]
    write_once(checkpoint_path, canonical(checkpoint))
    audit = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_oracle_scoring_authorization_checkpoint_audit.v1",
        "task": cfg["task"],
        "status": checkpoint["status"],
        "checkpoint_sha256": sha(checkpoint_path),
        "all_pinned_parent_hashes_match": True,
        "exact_calibration_scenes": len(scene_ids),
        "constrained_parent_graphs": len(inventory),
        "effective_semantic_logical_calls": execution_audit["recorded_logical_calls"],
        "pair_records": len(pair_records),
        "six_vote_groups": len(group_rows),
        "oracle_access": 0,
        "holdout_access": 0,
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "metrics_calculated": 0,
        "closure": 0,
    }
    audit_path = ROOT / cfg["outputs"]["audit"]
    write_once(audit_path, canonical(audit))
    report = """# P1V4 calibration look120 Oracle-scoring authorization checkpoint

This offline checkpoint freezes the exact 120 calibration scenes, 240 valid constrained-parent graph artifacts, Mini-medium response freeze, pair re-score, and six-vote groups for one later, separately authorized development-Oracle scoring operation.

It does not load an SCM or Oracle direction, calculate precision/coverage/gates, use holdout data, call the semantic API, rerun statistics, or apply closure. The next step requires explicit authorization to open only the calibration-development Oracle commitments and calculate the registered metrics.
"""
    report_path = ROOT / cfg["outputs"]["report"]
    if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
        raise RuntimeError(f"non-deterministic artifact drift: {report_path}")
    if not report_path.exists():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
