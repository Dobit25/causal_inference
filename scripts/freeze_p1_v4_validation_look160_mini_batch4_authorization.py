"""Freeze the explicitly authorized next 480-call validation slice."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_semantic_batch4.yaml"
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
    preflight_path = ROOT / cfg["parents"]["provider_preflight"]["path"]
    overlay_path = ROOT / cfg["parents"]["provider_incident_overlay"]["path"]
    for key, path in (("execution_plan", plan_path), ("provider_preflight", preflight_path), ("provider_incident_overlay", overlay_path)):
        if sha(path) != cfg["parents"][key]["sha256"]:
            raise RuntimeError(f"{key} hash drift")
    plan = load(plan_path)
    preflight = load(preflight_path)
    logical_ids = [row["logical_id"] for row in plan["logical_calls"]]
    cache_root = ROOT / cfg["runtime"]["cache_root"]
    raw_path = cache_root / "raw_responses.jsonl"
    ledger_path = cache_root / "token_ledger.jsonl"
    raw_ids = {row["logical_id"] for row in jsonl(raw_path)}
    overlay_ids = {row["logical_id"] for row in jsonl(overlay_path)}
    effective_ids = raw_ids | overlay_ids
    pending = [logical_id for logical_id in logical_ids if logical_id not in effective_ids]
    authorized = pending[:480]
    window = window_start()
    used = sum(int(row["total_tokens"]) for row in jsonl(ledger_path) if row.get("window_start") == window)
    checks = {
        "plan_hash": sha(plan_path) == cfg["parents"]["execution_plan"]["sha256"],
        "provider_preflight_pass": preflight.get("status") == "PASS",
        "exact_plan_calls": len(logical_ids) == len(set(logical_ids)) == 2640,
        "raw_cache_count": len(raw_ids) == 1440,
        "overlay_exactly_six": len(overlay_ids) == 6,
        "effective_cache_count": len(effective_ids) == 1440,
        "exact_next_slice": len(authorized) == 480 and authorized == pending[:480],
        "mini_medium_unchanged": all(row["model"] == cfg["semantic_contract"]["model"] and row["reasoning_effort"] == "medium" for row in plan["logical_calls"]),
        "daily_token_hard_stop": cfg["token_control"]["hard_stop_tokens"] == 3_000_000 and used < 3_000_000,
        "project_hard_stop": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "oracle_holdout_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False,
        "closure_forbidden": cfg["boundary"]["closure"] == "forbidden",
    }
    if not all(checks.values()):
        raise RuntimeError(f"batch4 authorization checks failed: {[key for key, value in checks.items() if not value]}")
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_checkpoint.v1",
        "status": "PASS_READY_NOT_EXECUTED",
        "checks": checks,
        "config_sha256": sha(CONFIG),
        "plan_sha256": sha(plan_path),
        "provider_preflight_sha256": sha(preflight_path),
        "overlay_sha256": sha(overlay_path),
        "runner_sha256": sha(RUNNER),
        "cache_before_execution": {"raw_records": len(raw_ids), "effective_records": len(effective_ids), "raw_sha256": sha(raw_path), "token_ledger_sha256": sha(ledger_path)},
        "token_window_start": window,
        "token_window_used_before_execution": used,
        "authorized_logical_ids": authorized,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    checkpoint_sha = write_new(ROOT / cfg["outputs"]["live_authorization_checkpoint"], checkpoint)
    authorization = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_authorization.v1",
        "status": "PASS_LIVE_AUTHORIZED",
        "explicit_user_live_authorization": True,
        "user_authorization_scope": "next batch, exactly 480 logical calls",
        "checkpoint_sha256": checkpoint_sha,
        "authorized_logical_calls": 2640,
        "execution_slice": {"batch_id": "look160_batch4_480", "max_new_calls": 480, "authorized_pending_logical_ids": authorized},
        "project_hard_stop_usd": 18.0,
        "daily_token_hard_stop": 3_000_000,
        "study_calls_recorded_before_execution": len(effective_ids),
        "new_calls_executed_at_freeze": 0,
    }
    auth_sha = write_new(ROOT / cfg["outputs"]["live_authorization"], authorization)
    audit = {"schema_version": "fourgraph.p1_v4_validation_look160_mini_batch4_authorization_audit.v1", "status": "PASS_BATCH4_AUTHORIZATION", "checks": checks, "config_sha256": sha(CONFIG), "checkpoint_sha256": checkpoint_sha, "authorization_sha256": auth_sha, "authorized_new_calls": 480, "executed_new_calls": 0, "effective_cached_calls": len(effective_ids), "oracle_access": 0, "holdout_access": 0}
    write_new(ROOT / cfg["outputs"]["live_authorization_audit"], audit)
    print(json.dumps({"status": audit["status"], "effective_cached_calls": len(effective_ids), "authorized_new_calls": 480, "token_window_used": used, "authorization_sha256": auth_sha}, indent=2))


if __name__ == "__main__":
    main()
