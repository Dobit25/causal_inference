"""Freeze the user-authorized second and third 480-call validation slices."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_semantic_live_batch23.yaml"
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


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_new(path: Path, value: object) -> str:
    body = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()


def current_window_start() -> str:
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    boundary = datetime.combine(now.date(), time(7), tzinfo=now.tzinfo)
    return (boundary if now >= boundary else boundary - timedelta(days=1)).isoformat()


def main() -> None:
    cfg = load(CONFIG)
    plan_path = ROOT / cfg["parents"]["execution_plan"]["path"]
    preflight_path = ROOT / cfg["parents"]["provider_preflight"]["path"]
    batch1_path = ROOT / cfg["parents"]["batch1_execution_audit"]["path"]
    if sha(plan_path) != cfg["parents"]["execution_plan"]["sha256"]:
        raise RuntimeError("execution plan hash drift")
    if sha(preflight_path) != cfg["parents"]["provider_preflight"]["sha256"]:
        raise RuntimeError("provider preflight hash drift")
    if sha(batch1_path) != cfg["parents"]["batch1_execution_audit"]["sha256"]:
        raise RuntimeError("batch1 audit hash drift")

    plan = load(plan_path)
    preflight = load(preflight_path)
    batch1 = load(batch1_path)
    logical_ids = [row["logical_id"] for row in plan["logical_calls"]]
    cache_root = ROOT / cfg["runtime"]["cache_root"]
    raw_path = cache_root / "raw_responses.jsonl"
    metadata_path = cache_root / "request_metadata.jsonl"
    ledger_path = cache_root / "token_ledger.jsonl"
    raw = rows(raw_path)
    cached_ids = [row["logical_id"] for row in raw]
    pending = logical_ids[len(cached_ids):]
    authorized = pending[: cfg["scope"]["authorized_new_calls"]]
    batch2 = authorized[: cfg["scope"]["batch_size"]]
    batch3 = authorized[cfg["scope"]["batch_size"] :]
    window = current_window_start()
    window_tokens = sum(int(row["total_tokens"]) for row in rows(ledger_path) if row.get("window_start") == window)

    checks = {
        "parents_hash_pinned": True,
        "preflight_pass": preflight.get("status") == "PASS",
        "batch1_pass": batch1.get("status") == "PASS_AUTHORIZED_SLICE_COMPLETE",
        "exact_plan_calls": len(logical_ids) == len(set(logical_ids)) == 2640,
        "exact_cached_prefix": cached_ids == logical_ids[:480],
        "cached_terminal_without_provider_error": len(raw) == 480 and all(row.get("status") != "provider_error" for row in raw),
        "cache_companions_complete": len(rows(metadata_path)) == 480 and len(rows(ledger_path)) == 481,
        "exact_authorized_slice": len(authorized) == 960 and len(batch2) == len(batch3) == 480,
        "mini_medium_unchanged": all(row["model"] == cfg["semantic_contract"]["model"] and row["reasoning_effort"] == "medium" for row in plan["logical_calls"]),
        "daily_token_hard_stop": cfg["token_control"]["hard_stop_tokens"] == 3_000_000,
        "current_window_below_stop": window_tokens < 3_000_000,
        "project_hard_stop": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "oracle_holdout_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False,
        "closure_forbidden": cfg["boundary"]["closure"] == "forbidden",
    }
    if not all(checks.values()):
        raise RuntimeError(f"authorization checks failed: {[key for key, value in checks.items() if not value]}")

    checkpoint = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_checkpoint.v1",
        "status": "PASS_READY_NOT_EXECUTED",
        "checks": checks,
        "plan_sha256": sha(plan_path),
        "provider_preflight_sha256": sha(preflight_path),
        "batch1_audit_sha256": sha(batch1_path),
        "runner_sha256": sha(RUNNER),
        "cache_before_execution": {
            "recorded_calls": 480,
            "raw_responses_sha256": sha(raw_path),
            "request_metadata_sha256": sha(metadata_path),
            "token_ledger_sha256": sha(ledger_path),
        },
        "token_window_start": window,
        "token_window_used_before_execution": window_tokens,
        "authorized_batches": [
            {"batch_id": "look160_batch2_480", "logical_ids": batch2},
            {"batch_id": "look160_batch3_480", "logical_ids": batch3},
        ],
        "oracle_access": 0,
        "holdout_access": 0,
    }
    checkpoint_path = ROOT / cfg["outputs"]["live_authorization_checkpoint"]
    checkpoint_sha = write_new(checkpoint_path, checkpoint)
    authorization = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_authorization.v1",
        "status": "PASS_LIVE_AUTHORIZED",
        "explicit_user_live_authorization": True,
        "user_authorization_scope": "batch 2 and 3, total 960 logical calls",
        "checkpoint_sha256": checkpoint_sha,
        "authorized_logical_calls": 2640,
        "execution_slice": {
            "batch_id": "look160_batch23_960",
            "max_new_calls": 960,
            "authorized_pending_logical_ids": authorized,
            "internal_batches": [
                {"batch_id": "look160_batch2_480", "count": 480},
                {"batch_id": "look160_batch3_480", "count": 480},
            ],
        },
        "project_hard_stop_usd": 18.0,
        "daily_token_hard_stop": 3_000_000,
        "study_calls_recorded_before_execution": 480,
        "new_calls_executed_at_freeze": 0,
    }
    authorization_path = ROOT / cfg["outputs"]["live_authorization"]
    authorization_sha = write_new(authorization_path, authorization)
    audit = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_batch23_authorization_audit.v1",
        "status": "PASS_BATCH23_AUTHORIZATION",
        "checks": checks,
        "config_sha256": sha(CONFIG),
        "checkpoint_sha256": checkpoint_sha,
        "authorization_sha256": authorization_sha,
        "authorized_new_calls": 960,
        "executed_new_calls": 0,
        "cached_calls": 480,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    write_new(ROOT / cfg["outputs"]["live_authorization_audit"], audit)
    report = (
        "# P1V4 validation look-160 Mini batches 2–3 authorization\n\n"
        "Status: **PASS_BATCH23_AUTHORIZATION**. Exactly the next 960 pending logical IDs are pinned as two 480-call batches. "
        "The first 480 cached calls are immutable and will not be rerun. Model, prompt, schema, stories, pair pools, agreement policy and scientific boundaries are unchanged.\n\n"
        f"Token window `{window}` contained {window_tokens:,}/3,000,000 provider-reported tokens at freeze. The runner checks usage after every call and at each 480-call boundary. "
        "Oracle, holdout, metrics and closure remain locked.\n"
    )
    report_path = ROOT / cfg["outputs"]["authorization_report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
        raise RuntimeError(f"artifact drift: {report_path}")
    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    print(json.dumps({"status": audit["status"], "cached": 480, "authorized_new_calls": 960, "token_window_used": window_tokens, "authorization_sha256": authorization_sha}, indent=2))


if __name__ == "__main__":
    main()
