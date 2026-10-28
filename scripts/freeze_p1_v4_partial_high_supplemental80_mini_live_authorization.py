"""Pin one preflight and the exact Mini-medium supplemental study-call identities."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/p1_v4_partial_high_supplemental80_mini_semantic_live.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_independent_calibration_look120_mini_semantic.py"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def window_start() -> str:
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    boundary = datetime.combine(now.date(), time(7), tzinfo=now.tzinfo)
    return (boundary if now >= boundary else boundary - timedelta(days=1)).isoformat()


def write_immutable(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    plan_path = ROOT / cfg["parents"]["execution_plan"]["path"]
    preflight_path = ROOT / cfg["parents"]["provider_preflight"]["path"]
    if sha(plan_path) != cfg["parents"]["execution_plan"]["sha256"]:
        raise RuntimeError("semantic plan hash drift")
    if sha(preflight_path) != cfg["parents"]["provider_preflight"]["sha256"]:
        raise RuntimeError("provider preflight hash drift")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    calls = plan["logical_calls"]
    logical_ids = [row["logical_id"] for row in calls]
    checks = {
        "provider_preflight_pass": preflight.get("status") == "PASS",
        "provider_preflight_nonstudy": preflight.get("study_execution") is False and preflight.get("study_scenes_loaded") == 0,
        "provider_preflight_synthetic_21_pairs": preflight.get("worst_case_nodes") == 7 and preflight.get("worst_case_pairs") == 21,
        "provider_preflight_model": preflight.get("model") == "gpt-5.4-mini-2026-03-17",
        "provider_preflight_usage": isinstance(preflight.get("total_tokens"), int) and preflight["total_tokens"] > 0,
        "exact_960_calls": len(calls) == cfg["scope"]["logical_calls"] == 960,
        "unique_ids": len(set(logical_ids)) == 960,
        "exact_80_scenes": len({row["study_id"] for row in calls}) == 80,
        "two_variants": {row["variant"] for row in calls} == {"full", "partial"},
        "mini_medium": all(row["model"] == "gpt-5.4-mini-2026-03-17" and row["reasoning_effort"] == "medium" for row in calls),
        "no_oracle_holdout": not cfg["boundary"]["oracle_access"] and not cfg["boundary"]["holdout_access"],
        "no_closure": cfg["boundary"]["closure"] == "forbidden",
        "hard_stop": cfg["token_control"]["hard_stop_tokens"] == 2500000,
        "no_existing_cache": not (ROOT / cfg["runtime"]["cache_root"] / "raw_responses.jsonl").exists(),
    }
    if not all(checks.values()):
        raise RuntimeError(f"authorization checks failed: {checks}")
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_mini_live_checkpoint.v1",
        "status": "PASS_READY", "checks": checks,
        "plan_sha256": sha(plan_path), "provider_preflight_sha256": sha(preflight_path),
        "runner_sha256": sha(RUNNER), "authorized_logical_ids": logical_ids,
        "token_hard_stop": 2500000,
        "preflight_tokens_debited": preflight["total_tokens"],
        "boundary": cfg["boundary"],
    }
    checkpoint_body = canonical(checkpoint)
    authorization = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_mini_live_authorization.v1",
        "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True,
        "checkpoint_sha256": hashlib.sha256(checkpoint_body).hexdigest().upper(),
        "authorized_logical_calls": 960,
        "execution_slice": {"max_new_calls": 960, "authorized_pending_logical_ids": logical_ids},
        "token_hard_stop": 2500000,
    }
    audit = {"status": "PASS", "checks": checks, "config_sha256": sha(CFG),
             "checkpoint_sha256": hashlib.sha256(checkpoint_body).hexdigest().upper(),
             "authorization_sha256": hashlib.sha256(canonical(authorization)).hexdigest().upper(),
             "provider_calls_before_study": 1,
             "provider_tokens_before_study": preflight["total_tokens"]}
    output = cfg["outputs"]
    write_immutable(ROOT / output["live_authorization_checkpoint"], checkpoint_body)
    write_immutable(ROOT / output["live_authorization"], canonical(authorization))
    write_immutable(ROOT / output["live_authorization_audit"], canonical(audit))
    ledger = ROOT / cfg["runtime"]["cache_root"] / "token_ledger.jsonl"
    if ledger.exists():
        raise RuntimeError("token ledger already exists before new authorization")
    write_immutable(ledger, canonical({
        "window_start": window_start(), "logical_id": "PROVIDER_PREFLIGHT",
        "input_tokens": preflight["input_tokens"],
        "output_tokens": preflight["output_tokens"],
        "reasoning_tokens": preflight["reasoning_tokens"],
        "total_tokens": preflight["total_tokens"],
        "remaining_tokens_after_call": 2500000 - preflight["total_tokens"], "cost_usd": None,
    }))
    print(json.dumps({"status": "PASS_LIVE_AUTHORIZED", "authorized_calls": 960,
                      "preflight_tokens_debited": preflight["total_tokens"]}, indent=2))


if __name__ == "__main__":
    main()
