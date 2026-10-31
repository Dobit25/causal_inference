"""Freeze and authorize exactly the remaining 720 look-160 logical calls."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_remaining720.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_mini_semantic.py"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix in {".yaml", ".yml"} else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"mapping expected: {path}")
    return value

def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def write_new(path: Path, value: object) -> str:
    body = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()

def main() -> None:
    cfg = load(CONFIG)
    plan_path = ROOT / cfg["parents"]["execution_plan"]["path"]
    preflight_path = ROOT / cfg["parents"]["provider_preflight"]["path"]
    raw_path = ROOT / cfg["parents"]["raw_responses"]["path"]
    overlay_path = ROOT / cfg["runtime"]["transport_retry_overlay"]["path"]
    for label, path, expected in (
        ("execution_plan", plan_path, cfg["parents"]["execution_plan"]["sha256"]),
        ("provider_preflight", preflight_path, cfg["parents"]["provider_preflight"]["sha256"]),
        ("raw_responses", raw_path, cfg["parents"]["raw_responses"]["sha256"]),
        ("merged_overlay", overlay_path, cfg["runtime"]["transport_retry_overlay"]["sha256"]),
    ):
        if sha(path) != expected:
            raise RuntimeError(f"{label} hash drift")
    plan = load(plan_path)
    logical_ids = [item["logical_id"] for item in plan["logical_calls"]]
    raw_rows = jsonl(raw_path)
    raw_ids = {row["logical_id"] for row in raw_rows}
    overlay_ids = {row["logical_id"] for row in jsonl(overlay_path)}
    effective_ids = raw_ids | overlay_ids
    pending = [logical_id for logical_id in logical_ids if logical_id not in effective_ids]
    if len(logical_ids) != 2640 or len(set(logical_ids)) != 2640:
        raise RuntimeError("plan must contain exactly 2640 unique logical IDs")
    checks = {
        "plan_exact_2640": len(logical_ids) == 2640 and len(set(logical_ids)) == 2640,
        "raw_records_exact_1920": len(raw_rows) == 1920 and len(raw_ids) == 1920,
        "merged_overlay_exact_13": len(overlay_ids) == 13,
        "effective_cached_exact_1920": len(effective_ids) == 1920,
        "pending_exact_720": len(pending) == 720,
        "provider_preflight_pass": load(preflight_path).get("status") == "PASS",
        "model_mini_medium": cfg["semantic_contract"]["model"] == "gpt-5.4-mini-2026-03-17" and cfg["semantic_contract"]["reasoning_effort"] == "medium",
        "no_chunking": cfg["semantic_contract"]["truncation"] == "disabled" and cfg["semantic_contract"]["automatic_prompt_chunking"] == "forbidden",
        "token_hard_stop": cfg["token_control"]["hard_stop_tokens"] == 3_000_000,
        "project_hard_stop": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "oracle_holdout_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False,
        "metrics_locked": cfg["boundary"]["metric_calculation"] is False and cfg["boundary"]["closure"] == "forbidden",
    }
    if not all(checks.values()):
        raise RuntimeError(f"authorization checks failed: {[k for k, v in checks.items() if not v]}")
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_remaining720_authorization_checkpoint.v1",
        "status": "PASS_READY_NOT_EXECUTED",
        "checks": checks,
        "config_sha256": sha(CONFIG),
        "runner_sha256": sha(RUNNER),
        "plan_sha256": sha(plan_path),
        "provider_preflight_sha256": sha(preflight_path),
        "raw_responses_sha256": sha(raw_path),
        "merged_overlay_sha256": sha(overlay_path),
        "cache_before_execution": {"raw_records": len(raw_rows), "effective_records": len(effective_ids)},
        "authorized_logical_ids": pending,
        "authorized_calls": 720,
        "api_calls_before_execution": 0,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    checkpoint_sha = write_new(ROOT / cfg["outputs"]["live_authorization_checkpoint"], checkpoint)
    auth = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_remaining720_authorization.v1",
        "status": "PASS_LIVE_AUTHORIZED",
        "explicit_user_live_authorization": True,
        "user_authorization_scope": "exactly the 720 logical calls remaining after effective overlay reconciliation",
        "checkpoint_sha256": checkpoint_sha,
        "authorized_logical_calls": 2640,
        "execution_slice": {"batch_id": "look160_remaining_720", "max_new_calls": 720, "authorized_pending_logical_ids": pending},
        "token_hard_stop": 3_000_000,
        "project_hard_stop_usd": 18.0,
        "new_calls_executed_at_freeze": 0,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    auth_sha = write_new(ROOT / cfg["outputs"]["live_authorization"], auth)
    audit = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_remaining720_authorization_audit.v1",
        "status": "PASS_REMAINING_720_AUTHORIZATION",
        "checks": checks,
        "config_sha256": sha(CONFIG),
        "checkpoint_sha256": checkpoint_sha,
        "authorization_sha256": auth_sha,
        "authorized_new_calls": 720,
        "executed_new_calls": 0,
        "effective_cached_calls": len(effective_ids),
        "oracle_access": 0,
        "holdout_access": 0,
        "metrics_calculated": False,
    }
    audit_sha = write_new(ROOT / cfg["outputs"]["live_authorization_audit"], audit)
    print(json.dumps({"status": audit["status"], "authorized_calls": 720, "pending": len(pending), "checkpoint_sha256": checkpoint_sha, "authorization_sha256": auth_sha, "audit_sha256": audit_sha}, indent=2))

if __name__ == "__main__":
    main()
