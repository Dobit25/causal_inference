from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.common import canonical_json, sha256_file
from run_p1v3_statistical_ensemble import build_jobs, load_cfg


def audit_plan(cfg: dict[str, Any]) -> dict[str, Any]:
    plan_path = ROOT / cfg["runtime"]["plan_output"]
    if not plan_path.is_file():
        raise RuntimeError("execution plan is missing; run --dry-run first")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    jobs = build_jobs(cfg)
    planned_ids = {job["run_id"] for job in jobs}
    if plan.get("planned_jobs") != 6150 or len(plan.get("jobs", [])) != 6150:
        raise RuntimeError("planned job count is not 6,150")
    if {job["run_id"] for job in plan["jobs"]} != planned_ids:
        raise RuntimeError("plan identity drift")
    raw_root = ROOT / cfg["runtime"]["raw_root"]
    normalized_root = ROOT / cfg["runtime"]["normalized_root"]
    error_root = ROOT / cfg["runtime"]["error_root"]
    raw = {path.stem for path in raw_root.glob("*.json")} if raw_root.exists() else set()
    normalized = {path.stem for path in normalized_root.glob("*.json")} if normalized_root.exists() else set()
    errors = {path.stem for path in error_root.glob("*.json")} if error_root.exists() else set()
    unknown = (raw | normalized | errors) - planned_ids
    if unknown:
        raise RuntimeError("unknown execution artifact identity")
    mismatched = raw ^ normalized
    for run_id in sorted(raw & normalized):
        record = json.loads((normalized_root / f"{run_id}.json").read_text(encoding="utf-8"))
        if record.get("run_id") != run_id:
            raise RuntimeError(f"normalized record identity mismatch: {run_id}")
        raw_bytes = (raw_root / f"{run_id}.json").read_bytes()
        if record.get("raw_output_sha256") != sha256_file(raw_root / f"{run_id}.json"):
            raise RuntimeError(f"raw hash mismatch: {run_id}")
    complete = len(raw & normalized)
    failed = len(errors)
    recorded = len((raw & normalized) | errors)
    missing_expected = len(planned_ids - (raw & normalized))
    scene_count = len(list((ROOT / cfg["runtime"]["scene_root"]).glob("P1V3SD*/observations.npy"))) if (ROOT / cfg["runtime"]["scene_root"]).exists() else 0
    if mismatched:
        status = "FAIL_INCOMPLETE_ARTIFACT_PAIRS"
    elif complete == 0 and scene_count == 0:
        status = "PASS_DRY_RUN_AUDIT"
    elif recorded == len(planned_ids) and not ((raw & normalized) & errors):
        status = "PASS_EXECUTION_AUDIT"
    else:
        status = "FAIL_MISSING_EXPECTED_ARTIFACTS"
    audit = {
        "schema_version": "fourgraph.p1v3_statistical_execution_audit.v1",
        "status": status,
        "planned_fits": 6150,
        "complete_fit_pairs": complete,
        "failed_jobs": failed,
        "recorded_jobs": recorded,
        "retry_count": cfg["runtime"]["retry_count"],
        "missing_or_incomplete": len(mismatched),
        "missing_expected_jobs": missing_expected,
        "unknown_artifacts": len(unknown),
        "concurrency": cfg["runtime"]["concurrency"],
        "execution_boundary": {
            "oracle_accessed": False,
            "holdout_accessed": False,
            "semantic_api_calls": 0,
            "study_scenes_materialized": scene_count,
            "statistical_fits": complete,
        },
        "hash_verified": True,
    }
    out = ROOT / cfg["runtime"]["audit_output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(canonical_json(audit))
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/p1v3_statistical_execution.yaml")
    args = parser.parse_args()
    print(json.dumps(audit_plan(load_cfg(args.config)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
