"""Freeze the user-authorized one-retry-per-provider-incident recovery overlay."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_provider_incident_recovery.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_mini_semantic.py"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


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
    body = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()


def window_start() -> str:
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    boundary = datetime.combine(now.date(), time(7), tzinfo=now.tzinfo)
    return (boundary if now >= boundary else boundary - timedelta(days=1)).isoformat()


def main() -> None:
    cfg = load(CONFIG)
    plan_path = ROOT / cfg["parents"]["execution_plan"]["path"]
    audit_path = ROOT / cfg["parents"]["watchdog_execution_audit"]["path"]
    raw_path = ROOT / cfg["parents"]["raw_responses"]["path"]
    for key, path in (("execution_plan", plan_path), ("watchdog_execution_audit", audit_path), ("raw_responses", raw_path)):
        if sha(path) != cfg["parents"][key]["sha256"]:
            raise RuntimeError(f"{key} hash drift")
    plan = load(plan_path)
    raw = jsonl(raw_path)
    errors = [row for row in raw if row.get("status") == "provider_error"]
    exact_ids = cfg["recovery_scope"]["logical_ids"]
    watchdog_test = load(ROOT / cfg["outputs"]["watchdog_self_test"])
    ledger_path = ROOT / cfg["runtime"]["cache_root"] / "token_ledger.jsonl"
    window = window_start()
    token_window = sum(int(row["total_tokens"]) for row in jsonl(ledger_path) if row.get("window_start") == window)
    overlay_path = ROOT / cfg["outputs"]["retry_overlay"]
    checks = {
        "exact_six_registered_ids": len(exact_ids) == 6 and len(set(exact_ids)) == 6,
        "raw_errors_exactly_registered": {row["logical_id"] for row in errors} == set(exact_ids),
        "registered_ids_in_plan": set(exact_ids).issubset({row["logical_id"] for row in plan["logical_calls"]}),
        "no_prior_overlay": not overlay_path.exists(),
        "one_attempt_per_id": cfg["recovery_scope"]["maximum_attempts_per_logical_id"] == 1,
        "original_errors_immutable": cfg["recovery_scope"]["overwrite_original_error"] == "forbidden",
        "watchdog_offline_self_test_pass": watchdog_test.get("status") == "PASS" and watchdog_test.get("no_api_calls") is True,
        "hard_token_budget_available": token_window < cfg["token_control"]["hard_stop_tokens"],
        "hard_spend_limit_enforced": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "oracle_holdout_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False,
    }
    if not all(checks.values()):
        raise RuntimeError(f"recovery authorization checks failed: {[key for key, value in checks.items() if not value]}")
    checkpoint = {"schema_version": "fourgraph.p1_v4_validation_look160_provider_incident_recovery_checkpoint.v1", "status": "PASS_READY_NOT_EXECUTED", "checks": checks, "plan_sha256": sha(plan_path), "raw_responses_sha256": sha(raw_path), "watchdog_execution_audit_sha256": sha(audit_path), "runner_sha256": sha(RUNNER), "watchdog_self_test_sha256": sha(ROOT / cfg["outputs"]["watchdog_self_test"]), "logical_ids": exact_ids, "token_window_start": window, "token_window_used_before_execution": token_window, "oracle_access": 0, "holdout_access": 0}
    checkpoint_sha = write_new(ROOT / cfg["outputs"]["authorization_checkpoint"], checkpoint)
    auth = {"schema_version": "fourgraph.p1_v4_validation_look160_provider_incident_recovery_authorization.v1", "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True, "checkpoint_sha256": checkpoint_sha, "logical_ids": exact_ids, "maximum_attempts_per_logical_id": 1, "retry_overlay_only": True, "project_hard_stop_usd": 18.0, "daily_token_hard_stop": 3000000, "no_auto_retry_after_failure": True}
    auth_sha = write_new(ROOT / cfg["outputs"]["authorization"], auth)
    audit = {"schema_version": "fourgraph.p1_v4_validation_look160_provider_incident_recovery_authorization_audit.v1", "status": "PASS_RECOVERY_AUTHORIZATION", "checks": checks, "config_sha256": sha(CONFIG), "checkpoint_sha256": checkpoint_sha, "authorization_sha256": auth_sha, "authorized_retries": 6, "oracle_access": 0, "holdout_access": 0}
    write_new(ROOT / cfg["outputs"]["authorization_audit"], audit)
    print(json.dumps({"status": audit["status"], "authorized_retries": 6, "token_window_before_execution": token_window, "authorization_sha256": auth_sha}, indent=2))


if __name__ == "__main__":
    main()
