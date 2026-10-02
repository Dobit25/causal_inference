from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def run(config_path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    audit_path = ROOT / cfg["phase_d_audit"]
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["phase_d_pass"] = audit.get("status") == "PASS_EXECUTION_AUDIT"
    checks["artifacts_complete"] = audit.get("complete_fit_pairs") == 6150 and audit.get("recorded_jobs") == 6150 and audit.get("missing_expected_jobs") == 0
    boundary = audit.get("execution_boundary", {})
    checks["oracle_zero"] = boundary.get("oracle_accessed") is False
    checks["holdout_zero"] = boundary.get("holdout_accessed") is False
    checks["semantic_api_zero"] = boundary.get("semantic_api_calls") == 0
    checks["historical_incidents_preserved"] = audit.get("historical_error_artifacts") == 60 and audit.get("superseded_error_artifacts") == 60
    protocol_path = ROOT / cfg["protocol_manifest"]
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    pool = protocol["semantic_shared_pool"]
    expected_pool = ["single_boss", "C1", "C2", "C3", "C4", "C5", "C6", "primary_ensemble"]
    checks["shared_pool_frozen"] = pool["source_conditions"] == expected_pool and pool["maximum_pairs_per_scene"] == 21 and pool["raw_response_reuse"] in (True, "required")
    checks["closure_is_condition_specific"] = pool["condition_specific_closure"] in (True, "required") and pool["global_closure_reuse"] in (False, "forbidden")
    checks["chunking_disabled"] = pool["automatic_prompt_chunking"] in (False, "forbidden")
    checks["prompt_hash_match"] = cfg["semantic"]["prompt"] == pool["prompt"]
    checks["schema_hash_available"] = (ROOT / cfg["semantic"]["schema"]).is_file()
    checks["model_frozen"] = cfg["semantic"]["model_snapshot"] == pool["model_snapshot"]
    checks["truncation_disabled"] = cfg["semantic"]["truncation"] == "disabled"
    checks["provider_preflight_not_executed"] = cfg["semantic"]["provider_preflight"] == "prepared_not_executed"
    hashes = {}
    for key, rel in {
        "phase_d_audit": cfg["phase_d_audit"],
        "protocol_manifest": cfg["protocol_manifest"],
        "algorithm_manifest": cfg["algorithm_manifest"],
        "prompt": cfg["semantic"]["prompt"],
        "schema": cfg["semantic"]["schema"],
        "execution_plan": "data/manifests/p1v3_statistical_execution_plan.json",
    }.items():
        hashes[key] = digest(ROOT / rel)
    passed = all(checks.values())
    result = {
        "schema_version": "fourgraph.p1v3_phase_e_shared_semantic_authorization_audit.v1",
        "task": cfg["task"],
        "status": "PASS_CHECKPOINT_NO_LIVE_EXECUTION" if passed else "FAIL_CHECKPOINT",
        "checks": checks,
        "hashes": hashes,
        "shared_semantic_pool": {
            "conditions": expected_pool,
            "maximum_pairs_per_scene": 21,
            "raw_response_reuse": True,
            "condition_specific_filtering": True,
            "condition_specific_closure": True,
        },
        "execution_boundary": {
            "provider_preflight_prepared": True,
            "provider_preflight_executed": False,
            "study_semantic_calls": 0,
            "oracle_accessed": False,
            "holdout_accessed": False,
        },
        "phase_e_live_authorized": False,
    }
    out = ROOT / "data/manifests/p1v3_phase_e_shared_semantic_authorization_audit.json"
    out.write_bytes(canonical(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs/p1v3_phase_e_shared_semantic_authorization_checkpoint.yaml")
    args = parser.parse_args()
    result = run(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"].startswith("PASS") else 1)
