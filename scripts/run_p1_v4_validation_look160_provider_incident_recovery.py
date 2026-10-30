"""Run the exact one-attempt recovery overlay for six provider incidents."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_p1_v4_independent_calibration_look120_mini_semantic as base  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_validation_look160_provider_incident_recovery.yaml"


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
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical(value))


def write_new(path: Path, value: object) -> str:
    body = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()


def main() -> None:
    cfg = load(CONFIG)
    auth_path = ROOT / cfg["outputs"]["authorization"]
    auth = load(auth_path)
    if auth.get("status") != "PASS_LIVE_AUTHORIZED" or auth.get("explicit_user_live_authorization") is not True:
        raise RuntimeError("explicit recovery authorization absent")
    if auth.get("logical_ids") != cfg["recovery_scope"]["logical_ids"]:
        raise RuntimeError("authorized recovery IDs drift")
    raw_path = ROOT / cfg["parents"]["raw_responses"]["path"]
    if sha(raw_path) != cfg["parents"]["raw_responses"]["sha256"]:
        raise RuntimeError("raw cache drift before recovery")
    raw = rows(raw_path)
    original_errors = {row["logical_id"]: row for row in raw if row.get("status") == "provider_error"}
    ids = cfg["recovery_scope"]["logical_ids"]
    if set(original_errors) != set(ids):
        raise RuntimeError("provider error set drift before recovery")
    overlay_path = ROOT / cfg["outputs"]["retry_overlay"]
    attempts_path = ROOT / cfg["outputs"]["retry_attempts"]
    ledger_path = ROOT / cfg["outputs"]["retry_token_ledger"]
    if overlay_path.exists() or attempts_path.exists() or ledger_path.exists():
        raise RuntimeError("recovery outputs already exist")
    jobs = {job["logical_id"]: job for job in base.build_jobs(cfg)}
    schema = json.loads((ROOT / cfg["semantic_contract"]["schema"]).read_text(encoding="utf-8"))
    used = base.current_window_tokens(ROOT / cfg["runtime"]["cache_root"] / "token_ledger.jsonl")
    limit = int(cfg["token_control"]["hard_stop_tokens"])
    attempt_rows: list[dict] = []
    for logical_id in ids:
        prior = original_errors[logical_id]
        if "InternalServerError" in prior.get("error_message", ""):
            time.sleep(int(cfg["recovery_scope"]["retry_after_policy"]["internal_server_error_520_minimum_elapsed_seconds"]))
        else:
            time.sleep(int(cfg["recovery_scope"]["retry_after_policy"]["api_connection_error_backoff_seconds"]))
        job = jobs[logical_id]
        started = time.perf_counter()
        try:
            result = base.watchdog_response(job, schema, cfg["runtime"]["external_watchdog"])
            raw_text = result["raw_text"]
            try:
                validation = base.validate_response_by_pair(json.loads(raw_text), job["pairs"], job["story"])
                status = "completed_valid" if validation["response_valid"] else "completed_pair_invalid"
            except Exception as exc:
                validation = {"response_valid": False, "pairs": [], "validation_exception": f"{type(exc).__name__}: {exc}"}
                status = "completed_schema_invalid"
            record = {"logical_id": logical_id, "status": status, "scene_id": job["study_id"], "variant": job["variant"], "prompt_id": job["prompt_id"], "model": result["model"], "reasoning_effort": job["reasoning_effort"], "request_id": result["request_id"], "input_tokens": result["input_tokens"], "output_tokens": result["output_tokens"], "reasoning_tokens": result["reasoning_tokens"], "total_tokens": result["total_tokens"], "latency_ms": round((time.perf_counter() - started) * 1000), "response_sha256": base.sha_text(raw_text), "story_content_sha256": job["story_content_sha256"], "pair_pool_sha256": job["pair_pool_sha256"], "prompt_render_sha256": job["prompt_render_sha256"], "raw_text": raw_text, "response_valid": validation["response_valid"], "valid_pair_count": sum(row.get("pair_valid") is True for row in validation.get("pairs", [])), "invalid_pair_count": sum(row.get("pair_valid") is False for row in validation.get("pairs", [])), "retry_of_status": "provider_error", "retry_attempt_number": 1, "external_watchdog": True}
            append(overlay_path, record)
            used += record["total_tokens"]
            append(ledger_path, {"window_start": base.window_start(base.datetime.now(tz=base.ZoneInfo("Asia/Ho_Chi_Minh"))).isoformat(), "logical_id": logical_id, "input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"], "reasoning_tokens": record["reasoning_tokens"], "total_tokens": record["total_tokens"], "remaining_tokens_after_call": max(0, limit - used), "cost_usd": None, "retry_of_status": "provider_error"})
        except Exception as exc:
            record = {"logical_id": logical_id, "status": "provider_error", "scene_id": job["study_id"], "variant": job["variant"], "prompt_id": job["prompt_id"], "model": job["model"], "reasoning_effort": job["reasoning_effort"], "error_type": type(exc).__name__, "error_message": str(exc)[:1000], "latency_ms": round((time.perf_counter() - started) * 1000), "retry_of_status": "provider_error", "retry_attempt_number": 1, "external_watchdog": True}
        append(attempts_path, record)
        attempt_rows.append(record)
        if used >= limit:
            break
    succeeded = [row for row in attempt_rows if row.get("status") != "provider_error"]
    failed = [row for row in attempt_rows if row.get("status") == "provider_error"]
    audit = {"schema_version": "fourgraph.p1_v4_validation_look160_provider_incident_recovery_execution_audit.v1", "status": "PASS_ALL_RECOVERED" if len(succeeded) == 6 else "INCOMPLETE_RECOVERY_FAILURES", "authorized_ids": ids, "attempted_ids": [row["logical_id"] for row in attempt_rows], "succeeded": len(succeeded), "failed": len(failed), "failed_ids": [row["logical_id"] for row in failed], "retry_overlay_sha256": sha(overlay_path) if overlay_path.exists() else None, "retry_attempts_sha256": sha(attempts_path), "retry_token_ledger_sha256": sha(ledger_path) if ledger_path.exists() else None, "provider_usage_successes": {key: sum(int(row.get(key, 0) or 0) for row in succeeded) for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")}, "oracle_access": 0, "holdout_access": 0, "metrics_calculated": False}
    write_new(ROOT / cfg["outputs"]["execution_audit"], audit)
    report = ("# P1V4 validation look-160 provider-incident recovery\n\n"
              f"Status: **{audit['status']}**. Authorized recovery attempts: 6; succeeded: {audit['succeeded']}; failed: {audit['failed']}. Original provider-error records remain immutable. Successful responses exist only in the separately hashed retry overlay. Oracle, holdout, closure and metrics remain locked.\n")
    report_path = ROOT / cfg["outputs"]["report"]
    if report_path.exists() and report_path.read_text(encoding="utf-8") != report:
        raise RuntimeError("report drift")
    if not report_path.exists():
        report_path.write_text(report, encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
