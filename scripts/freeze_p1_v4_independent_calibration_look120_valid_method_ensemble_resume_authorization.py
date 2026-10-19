"""Freeze exact missing identities before any valid-method Phase-D resume."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_authorization.yaml"
PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_statistical_parent_plan.json"
AMENDMENT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_amendment.json"
AMENDMENT_AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_amendment_audit.json"
DRY_AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_dry_run_audit.json"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_statistical.py"
RAW = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/raw"
NORM = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/normalized"
ERROR = ROOT / "results/raw/p1_v4_independent_calibration/look120/statistical/errors/D823FF5FBE1D32979100E7E9185DEF94468A04F7569B8966F6A911FFB51B7DAC.json"
RESUME_PLAN = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_plan.json"
CHECKPOINT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_authorization_checkpoint.json"
AUDIT = ROOT / "data/manifests/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_authorization_audit.json"
REPORT = ROOT / "reports/p1_v4_independent_calibration_look120_valid_method_ensemble_resume_authorization.md"


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise RuntimeError(f"artifact drift: {path.relative_to(ROOT)}")
    if not path.exists(): path.write_bytes(data)


def build() -> tuple[dict, dict, dict, str]:
    source = json.loads(PLAN.read_text(encoding="utf-8"))
    jobs = source["jobs"]
    job_ids = {job["execution_id"] for job in jobs}
    raw_ids = {path.stem for path in RAW.glob("*.json")}
    norm_ids = {path.stem for path in NORM.glob("*.json")}
    if raw_ids != norm_ids or not raw_ids.issubset(job_ids):
        raise RuntimeError("terminal cache is not a clean subset of the frozen plan")
    if len(raw_ids) != 2037 or not ERROR.is_file():
        raise RuntimeError("unexpected pre-resume cache state")
    missing = [job for job in jobs if job["execution_id"] not in raw_ids]
    if len(missing) != 22683:
        raise RuntimeError(f"expected 22683 missing identities, found {len(missing)}")
    resume_plan = {
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_VALID_METHOD_ENSEMBLE_RESUME",
        "source_plan_sha256": sha(PLAN),
        "terminal_cached_execution_identities": len(raw_ids),
        "missing_execution_identities": len(missing),
        "jobs": missing,
        "boundary": {"semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0},
    }
    checkpoint = {
        "task": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_VALID_METHOD_ENSEMBLE_RESUME_LIVE_AUTHORIZATION_CHECKPOINT",
        "status": "READY_FOR_EXPLICIT_LIVE_AUTHORIZATION",
        "dependencies": {
            "config_sha256": sha(CONFIG), "amendment_sha256": sha(AMENDMENT), "amendment_audit_sha256": sha(AMENDMENT_AUDIT),
            "dry_run_audit_sha256": sha(DRY_AUDIT), "runner_sha256": sha(RUNNER), "resume_plan_sha256": hashlib.sha256(canonical(resume_plan)).hexdigest().upper(),
            "historical_pc_error_sha256": sha(ERROR),
        },
        "authorization_if_explicitly_granted": {"exact_missing_execution_identities": len(missing), "cached_terminal_identities_not_rerun": len(raw_ids), "semantic_api_calls": False, "oracle_access": False, "holdout_access": False, "concurrency": 1, "automatic_retry": False},
    }
    audit = {
        "task": checkpoint["task"], "status": "PASS", "planned_total": len(jobs), "cached_terminal": len(raw_ids), "exact_missing": len(missing),
        "duplicate_execution_identities": 0, "unknown_cached_execution_identities": 0, "historical_pc_error_retained": True,
        "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0, "checkpoint_sha256": hashlib.sha256(canonical(checkpoint)).hexdigest().upper(),
    }
    report = f"""# Valid-method ensemble resume authorization checkpoint\n\nThe frozen Phase-D plan contains {len(jobs):,} identities. The stopped run already\nhas {len(raw_ids):,} terminal raw/normalized artifact pairs; exactly {len(missing):,}\nidentities remain. This checkpoint permits no execution by itself.\n\nIf and only if explicit live authorization is recorded, the runner may execute the\nexact missing list at concurrency one. Cached terminal identities are never rerun.\nThe historical PC error artifact is retained as incident evidence; the amended runner\nwill record any new invalid graph as `INVALID_NO_VOTE` rather than repairing it.\n"""
    return resume_plan, checkpoint, audit, report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    for path in (CONFIG, PLAN, AMENDMENT, AMENDMENT_AUDIT, DRY_AUDIT, RUNNER, ERROR):
        if not path.is_file(): raise SystemExit(f"missing dependency: {path}")
    plan, checkpoint, audit, report = build()
    if args.check:
        expected = ((RESUME_PLAN, canonical(plan)), (CHECKPOINT, canonical(checkpoint)), (AUDIT, canonical(audit)), (REPORT, report.encode("utf-8")))
        if any(not path.is_file() or path.read_bytes() != content for path, content in expected): raise SystemExit("resume checkpoint replay mismatch")
        print(json.dumps({"status": "PASS_CHECK", "exact_missing": len(plan["jobs"])})); return
    write_once(RESUME_PLAN, canonical(plan)); write_once(CHECKPOINT, canonical(checkpoint)); write_once(AUDIT, canonical(audit)); write_once(REPORT, report.encode("utf-8"))
    print(json.dumps({"status": "PASS", "exact_missing": len(plan["jobs"]), "live_status": checkpoint["status"]}))


if __name__ == "__main__": main()
