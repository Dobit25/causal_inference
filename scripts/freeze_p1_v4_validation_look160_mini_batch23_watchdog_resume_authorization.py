"""Freeze the second exact retry and watchdog-protected remaining batch scope."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_semantic_batch23_watchdog_resume.yaml"
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
    incident1_path = ROOT / cfg["parents"]["first_transport_incident"]["path"]
    incident2_path = ROOT / cfg["parents"]["second_transport_incident"]["path"]
    for key, path in (("execution_plan", plan_path), ("first_transport_incident", incident1_path), ("second_transport_incident", incident2_path)):
        if sha(path) != cfg["parents"][key]["sha256"]:
            raise RuntimeError(f"{key} hash drift")
    plan = load(plan_path)
    incident1, incident2 = load(incident1_path), load(incident2_path)
    cache_root = ROOT / cfg["runtime"]["cache_root"]
    raw_path, ledger_path = cache_root / "raw_responses.jsonl", cache_root / "token_ledger.jsonl"
    raw = jsonl(raw_path)
    logical_ids = [row["logical_id"] for row in plan["logical_calls"]]
    cached_ids = [row["logical_id"] for row in raw]
    pending = logical_ids[len(cached_ids):]
    retry_id = "P1V4SV475/ambiguous/P2"
    authorized = pending[: cfg["scope"]["authorized_new_calls"]]
    current_window = window_start()
    current_tokens = sum(int(row["total_tokens"]) for row in jsonl(ledger_path) if row.get("window_start") == current_window)
    watchdog = cfg["runtime"]["external_watchdog"]
    checks = {
        "first_retry_historical_success": incident1.get("logical_id") == "P1V4SV303/ambiguous/P5",
        "second_incident_is_exact_unrecorded_call": incident2.get("logical_id") == retry_id and incident2.get("evidence", {}).get("response_available") is False,
        "exact_cached_prefix": cached_ids == logical_ids[:877],
        "incident_is_next_pending": pending[0] == retry_id,
        "exact_authorized_scope": len(authorized) == 563 and authorized[0] == retry_id,
        "exactly_one_new_retry": cfg["scope"]["authorized_retry_calls"] == 1 and cfg["runtime"]["transport_retry"] == "exactly_one_for_P1V4SV475_ambiguous_P2",
        "watchdog_enabled_and_bounded": watchdog.get("enabled") is True and watchdog.get("sdk_attempt_timeout_seconds") == 120 and watchdog.get("worker_deadline_seconds") == 210,
        "mini_medium_unchanged": all(row["model"] == cfg["semantic_contract"]["model"] and row["reasoning_effort"] == "medium" for row in plan["logical_calls"]),
        "token_budget_available": current_tokens < cfg["token_control"]["hard_stop_tokens"],
        "hard_spend_stop": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "oracle_holdout_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False,
    }
    if not all(checks.values()):
        raise RuntimeError(f"watchdog authorization checks failed: {[key for key, value in checks.items() if not value]}")
    checkpoint = {"schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_watchdog_resume_checkpoint.v1", "status": "PASS_READY_NOT_EXECUTED", "checks": checks, "plan_sha256": sha(plan_path), "first_incident_sha256": sha(incident1_path), "second_incident_sha256": sha(incident2_path), "runner_sha256": sha(RUNNER), "cache_before_resume": {"recorded_calls": 877, "raw_responses_sha256": sha(raw_path), "token_ledger_sha256": sha(ledger_path)}, "token_window_start": current_window, "token_window_used_before_resume": current_tokens, "retry_logical_id": retry_id, "resume_logical_ids": authorized, "oracle_access": 0, "holdout_access": 0}
    checkpoint_sha = write_new(ROOT / cfg["outputs"]["live_authorization_checkpoint"], checkpoint)
    auth = {"schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_watchdog_resume_authorization.v1", "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True, "explicit_retry_authorization": {"logical_id": retry_id, "maximum_attempts": 1, "prior_attempt_produced_response": False, "prior_attempt_produced_usage": False}, "watchdog": watchdog, "checkpoint_sha256": checkpoint_sha, "authorized_logical_calls": 2640, "execution_slice": {"batch_id": "look160_batch23_watchdog_resume_563", "max_new_calls": 563, "authorized_pending_logical_ids": authorized}, "project_hard_stop_usd": 18.0, "daily_token_hard_stop": 3_000_000, "study_calls_recorded_before_execution": 877}
    auth_sha = write_new(ROOT / cfg["outputs"]["live_authorization"], auth)
    audit = {"schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_watchdog_resume_authorization_audit.v1", "status": "PASS_WATCHDOG_RETRY_AND_RESUME_AUTHORIZATION", "checks": checks, "config_sha256": sha(CONFIG), "checkpoint_sha256": checkpoint_sha, "authorization_sha256": auth_sha, "retry_calls": 1, "remaining_calls": 562, "oracle_access": 0, "holdout_access": 0}
    write_new(ROOT / cfg["outputs"]["live_authorization_audit"], audit)
    report = ("# P1V4 validation Mini: watchdog retry and resume authorization\n\n"
              "Status: **PASS_WATCHDOG_RETRY_AND_RESUME_AUTHORIZATION**. The user authorized one retry of `P1V4SV475/ambiguous/P2` and continuation of the 562 remaining IDs in the original batch-2/3 scope. Each request uses a separate worker with a 120-second SDK attempt timeout and a 210-second parent deadline. On any future deadline, the worker is terminated, a provider-error record is written, and no retry occurs automatically.\n")
    report_path = ROOT / cfg["outputs"]["authorization_report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
        raise RuntimeError(f"artifact drift: {report_path}")
    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"status": audit["status"], "retry_logical_id": retry_id, "authorized_new_calls": 563, "token_window_before_resume": current_tokens, "authorization_sha256": auth_sha}, indent=2))


if __name__ == "__main__":
    main()
