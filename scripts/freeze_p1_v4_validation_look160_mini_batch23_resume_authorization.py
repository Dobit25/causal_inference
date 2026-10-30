"""Freeze one explicit transport retry and resume scope for validation look-160."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_semantic_batch23_resume.yaml"
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
    prior_auth_path = ROOT / cfg["parents"]["batch23_authorization"]["path"]
    incident_path = ROOT / cfg["parents"]["transport_incident"]["path"]
    for key, path in (("execution_plan", plan_path), ("batch23_authorization", prior_auth_path), ("transport_incident", incident_path)):
        if sha(path) != cfg["parents"][key]["sha256"]:
            raise RuntimeError(f"{key} hash drift")

    plan = load(plan_path)
    prior_auth = load(prior_auth_path)
    incident = load(incident_path)
    raw_path = ROOT / cfg["runtime"]["cache_root"] / "raw_responses.jsonl"
    ledger_path = ROOT / cfg["runtime"]["cache_root"] / "token_ledger.jsonl"
    raw = jsonl(raw_path)
    logical_ids = [row["logical_id"] for row in plan["logical_calls"]]
    cached_ids = [row["logical_id"] for row in raw]
    pending = logical_ids[len(cached_ids):]
    retry_id = "P1V4SV303/ambiguous/P5"
    authorized = pending[: cfg["scope"]["authorized_new_calls"]]
    current_window = window_start()
    current_tokens = sum(int(row["total_tokens"]) for row in jsonl(ledger_path) if row.get("window_start") == current_window)
    checks = {
        "prior_authorization_pass": prior_auth.get("status") == "PASS_LIVE_AUTHORIZED",
        "incident_is_exact_unrecorded_call": incident.get("logical_id") == retry_id and incident.get("evidence", {}).get("response_available") is False,
        "exact_cached_prefix": cached_ids == logical_ids[:664],
        "incident_is_next_pending": pending[0] == retry_id,
        "exact_authorized_scope": len(authorized) == 776 and authorized[0] == retry_id,
        "one_retry_only": cfg["scope"]["authorized_retry_calls"] == 1 and cfg["runtime"]["transport_retry"] == "exactly_one_for_P1V4SV303_ambiguous_P5",
        "mini_medium_unchanged": all(row["model"] == cfg["semantic_contract"]["model"] and row["reasoning_effort"] == "medium" for row in plan["logical_calls"]),
        "timeout_is_technical_only": cfg["runtime"]["request_timeout_seconds"] == 180,
        "token_budget_available": current_tokens < cfg["token_control"]["hard_stop_tokens"],
        "hard_spend_stop": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "oracle_holdout_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False,
    }
    if not all(checks.values()):
        raise RuntimeError(f"resume authorization checks failed: {[key for key, value in checks.items() if not value]}")

    checkpoint = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_resume_checkpoint.v1",
        "status": "PASS_READY_NOT_EXECUTED",
        "checks": checks,
        "plan_sha256": sha(plan_path),
        "prior_authorization_sha256": sha(prior_auth_path),
        "transport_incident_sha256": sha(incident_path),
        "runner_sha256": sha(RUNNER),
        "cache_before_resume": {"recorded_calls": 664, "raw_responses_sha256": sha(raw_path), "token_ledger_sha256": sha(ledger_path)},
        "token_window_start": current_window,
        "token_window_used_before_resume": current_tokens,
        "retry_logical_id": retry_id,
        "resume_logical_ids": authorized,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    checkpoint_sha = write_new(ROOT / cfg["outputs"]["live_authorization_checkpoint"], checkpoint)
    auth = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_resume_authorization.v1",
        "status": "PASS_LIVE_AUTHORIZED",
        "explicit_user_live_authorization": True,
        "explicit_retry_authorization": {"logical_id": retry_id, "maximum_attempts": 1, "prior_attempt_produced_response": False, "prior_attempt_produced_usage": False},
        "checkpoint_sha256": checkpoint_sha,
        "authorized_logical_calls": 2640,
        "execution_slice": {"batch_id": "look160_batch23_resume_776", "max_new_calls": 776, "authorized_pending_logical_ids": authorized},
        "project_hard_stop_usd": 18.0,
        "daily_token_hard_stop": 3_000_000,
        "study_calls_recorded_before_execution": 664,
    }
    auth_sha = write_new(ROOT / cfg["outputs"]["live_authorization"], auth)
    audit = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_resume_authorization_audit.v1",
        "status": "PASS_RETRY_AND_RESUME_AUTHORIZATION",
        "checks": checks,
        "config_sha256": sha(CONFIG),
        "checkpoint_sha256": checkpoint_sha,
        "authorization_sha256": auth_sha,
        "retry_calls": 1,
        "remaining_calls": 775,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    write_new(ROOT / cfg["outputs"]["live_authorization_audit"], audit)
    report = (
        "# P1V4 validation Mini: retry and resume authorization\n\n"
        "Status: **PASS_RETRY_AND_RESUME_AUTHORIZATION**. The user authorized exactly one re-attempt of `P1V4SV303/ambiguous/P5`, which previously produced neither response nor provider usage, then a cache-resume of 775 subsequent IDs. A 180-second client transport timeout is a technical safety control only; the model, reasoning effort, prompt, schema, story, pair pool and scientific rules remain unchanged. Any further transport retry remains forbidden.\n"
    )
    report_path = ROOT / cfg["outputs"]["authorization_report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
        raise RuntimeError(f"artifact drift: {report_path}")
    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"status": audit["status"], "retry_logical_id": retry_id, "authorized_new_calls": 776, "token_window_before_resume": current_tokens, "authorization_sha256": auth_sha}, indent=2))


if __name__ == "__main__":
    main()
