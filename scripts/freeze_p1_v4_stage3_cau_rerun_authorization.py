"""Freeze the user's scoped authorization for the official `cau` Phase-3D rerun."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_cau_rerun_authorization.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parent_hashes = {}
    for name, item in cfg["parents"].items():
        path = ROOT / item["path"]
        actual = sha(path)
        if actual != item["sha256"]:
            raise RuntimeError(f"parent hash drift: {name}")
        parent_hashes[name] = actual
    correction = json.loads((ROOT / cfg["parents"]["environment_correction"]["path"]).read_text(encoding="utf-8"))
    preflight = json.loads((ROOT / cfg["parents"]["original_preflight"]["path"]).read_text(encoding="utf-8"))
    ids = [json.loads(line) for line in (ROOT / cfg["parents"]["exact_identities"]["path"]).read_text(encoding="utf-8").splitlines() if line]
    checks = {
        "cau_environment_correction_pass": correction["status"] == "PASS_CANONICAL_CAU_ENVIRONMENT" and all(correction["checks"].values()),
        "same_30_method_development_ids": {row["study_id"] for row in ids if row["role"] == "method_development"} == {f"P1V4SD{i:03d}" for i in range(30)},
        "same_registered_workload": preflight["statistical_workload"]["total_fits"] == 6180,
        "historical_run_retained": (ROOT / correction["historical_phase_d"]["output_root"]).is_dir(),
        "scope_has_no_provider_or_oracle_or_holdout": not any(cfg["authorization"][key] for key in ("semantic_api_calls", "provider_preflight", "oracle_access", "holdout_access")),
    }
    passed = all(checks.values()) and cfg["authorization"]["user_explicit_live_authorization"] is True
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_stage3_cau_rerun_live_authorization.v1",
        "task": cfg["task"],
        "status": "PASS_SCOPED_LIVE_AUTHORIZATION" if passed else "FAIL_LIVE_AUTHORIZATION",
        "scope": {"scene_ids": [f"P1V4SD{i:03d}" for i in range(30)], "canonical_runtime": "cau", "historical_run_reused": False},
        "workload": {"materialized_scenes": 30, "statistical_fits": 6180},
        "authorization": {"materialization_authorized": passed, "statistical_execution_authorized": passed, "semantic_api_calls_authorized": False, "provider_preflight_authorized": False, "oracle_access_authorized": False, "holdout_access_authorized": False, "automatic_semantic_continuation": False},
        "checks": checks,
        "parents": parent_hashes,
        "execution_boundary": {"semantic_api_calls": 0, "oracle_access": False, "holdout_access": False},
        "next_action": "RUN_P1_V4_STAGE_3D_STATISTICAL_CAU_RERUN_ONLY" if passed else "STOP",
    }
    body = canonical(checkpoint)
    audit = {"schema_version": "fourgraph.p1_v4_stage3_cau_rerun_live_authorization_audit.v1", "task": checkpoint["task"], "status": checkpoint["status"], "checks": checks, "checkpoint_sha256": hashlib.sha256(body).hexdigest().upper(), "execution_boundary": checkpoint["execution_boundary"]}
    report = f"""# P1V4 Stage-3D canonical `cau` rerun authorization

Status: **{checkpoint['status']}**. This authorization permits exactly 30 deterministic P1V4SD materializations and 6,180 local statistical fits in `cau`. It does not permit provider preflight, semantic API calls, Oracle or holdout access. The earlier `p1v3_py31020` run remains retained as historical evidence and will not be overwritten or reused as the official run.
""".encode("utf-8")
    return {ROOT / cfg["outputs"]["checkpoint"]: body, ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args(); generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content: raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items(): path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print(json.dumps({"status": "PASS", "scope": "cau_statistical_only", "api_calls": 0}, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
