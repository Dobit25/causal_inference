"""Execute only the separately authorized one-time retries for missing transport responses."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.semantic_sentence_id_contract import validate_response_by_pair  # noqa: E402
from scripts.run_p1_v4_independent_calibration_look120_mini_semantic import (  # noqa: E402
    build_jobs, canonical, load_key, sha_file, sha_text, window_start,
)

CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_transport_retry_amendment.yaml"


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical(row))


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_once(path: Path, value: object) -> None:
    payload = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(payload)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    raw_path = ROOT / cfg["parent_raw_response_cache"]["path"]
    audit_path = ROOT / cfg["parent_execution_audit"]["path"]
    if sha_file(raw_path) != cfg["parent_raw_response_cache"]["sha256"] or sha_file(audit_path) != cfg["parent_execution_audit"]["sha256"]:
        raise RuntimeError("frozen parent cache/audit hash drift")
    raw = load_jsonl(raw_path)
    errors = [row for row in raw if row.get("status") == "provider_error"]
    ids = [row.get("logical_id") for row in errors]
    if ids != ["P1V4SC237/full/P6", "P1V4SC237/partial/P1"]:
        raise RuntimeError("eligible incident identity drift")
    if any(row.get("error_type") != cfg["retry_policy"]["eligible_error_type"] or row.get("request_id") is not None or row.get("total_tokens") is not None for row in errors):
        raise RuntimeError("incident is not an eligible no-usage transport error")
    retry_path = ROOT / cfg["outputs"]["retry_responses"]
    if retry_path.exists() and retry_path.read_text(encoding="utf-8").strip():
        raise RuntimeError("retry artifact already exists; no duplicate retry is permitted")
    disposition = {"task": cfg["task"], "status": "PASS_DISPOSITIONED_FOR_ONE_RETRY_EACH", "parent_raw_sha256": sha_file(raw_path), "eligible_logical_ids": ids, "eligible_count": 2, "original_records": [{key: row.get(key) for key in ("logical_id", "status", "error_type", "error_message", "latency_ms", "story_content_sha256", "pair_pool_sha256", "prompt_render_sha256")} for row in errors], "no_response_or_usage": True, "oracle_access": 0, "holdout_access": 0}
    disposition_path = ROOT / cfg["outputs"]["disposition"]
    write_once(disposition_path, disposition)
    authorization = {"task": cfg["task"], "status": "PASS_LIVE_AUTHORIZED", "explicit_user_live_authorization": True, "config_sha256": sha_file(CONFIG), "disposition_sha256": sha_file(disposition_path), "authorized_logical_ids": ids, "max_new_attempts_per_logical_call": 1, "retry_timeout_seconds": cfg["retry_policy"]["timeout_seconds"], "boundary": cfg["boundary"]}
    write_once(ROOT / cfg["outputs"]["retry_authorization"], authorization)

    jobs = {job["logical_id"]: job for job in build_jobs({"parents": {"execution_plan": cfg["execution_plan"]}, "scope": {"logical_calls": 2160}, "semantic_contract": cfg["semantic_contract"]})}
    schema = json.loads((ROOT / cfg["semantic_contract"]["schema"]).read_text(encoding="utf-8"))
    client = OpenAI(api_key=load_key(), max_retries=0, timeout=float(cfg["retry_policy"]["timeout_seconds"]))
    ledger = raw_path.parent / "token_ledger.jsonl"
    rows: list[dict] = []
    for logical_id in ids:
        job = jobs[logical_id]; started = time.perf_counter()
        try:
            response = client.responses.create(model=job["model"], input=job["prompt"], reasoning={"effort": job["reasoning_effort"]}, max_output_tokens=8192, service_tier="default", store=False, text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": schema, "strict": True}}, metadata={"task": cfg["task"], "logical_id": logical_id, "study_execution": "true", "retry_attempt": "1"})
            usage = response.usage; total = getattr(usage, "total_tokens", None)
            if not isinstance(total, int):
                raise RuntimeError("missing provider-reported total_tokens")
            raw_text = response.output_text or ""
            validation = validate_response_by_pair(json.loads(raw_text), job["pairs"], job["story"])
            status = "completed_valid" if validation["response_valid"] else "completed_pair_invalid"
            row = {"logical_id": logical_id, "attempt": 2, "retry_of_status": "provider_error", "status": status, "scene_id": job["study_id"], "variant": job["variant"], "prompt_id": job["prompt_id"], "model": response.model, "reasoning_effort": job["reasoning_effort"], "request_id": getattr(response, "_request_id", None), "input_tokens": int(usage.input_tokens), "output_tokens": int(usage.output_tokens), "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0), "total_tokens": total, "latency_ms": round((time.perf_counter() - started) * 1000), "response_sha256": sha_text(raw_text), "story_content_sha256": job["story_content_sha256"], "pair_pool_sha256": job["pair_pool_sha256"], "prompt_render_sha256": job["prompt_render_sha256"], "raw_text": raw_text, "response_valid": validation["response_valid"], "valid_pair_count": sum(item.get("pair_valid") is True for item in validation["pairs"]), "invalid_pair_count": sum(item.get("pair_valid") is False for item in validation["pairs"])}
            window = window_start(datetime.now(tz=ZoneInfo("Asia/Ho_Chi_Minh"))).isoformat()
            append(ledger, {"window_start": window, "logical_id": logical_id, "attempt": 2, "record_type": "authorized_transport_retry", "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"], "reasoning_tokens": row["reasoning_tokens"], "total_tokens": row["total_tokens"], "cost_usd": None})
        except Exception as exc:
            row = {"logical_id": logical_id, "attempt": 2, "retry_of_status": "provider_error", "status": "provider_error", "scene_id": job["study_id"], "variant": job["variant"], "prompt_id": job["prompt_id"], "model": job["model"], "reasoning_effort": job["reasoning_effort"], "error_type": type(exc).__name__, "error_message": str(exc)[:1000], "latency_ms": round((time.perf_counter() - started) * 1000), "story_content_sha256": job["story_content_sha256"], "pair_pool_sha256": job["pair_pool_sha256"], "prompt_render_sha256": job["prompt_render_sha256"]}
        append(retry_path, row); rows.append(row)
        if row["status"] == "provider_error":
            break
        time.sleep(3.2)
    audit = {"task": cfg["task"], "authorized_retries": 2, "recorded_retries": len(rows), "retry_statuses": [row["status"] for row in rows], "all_resolved": len(rows) == 2 and all(row["status"] != "provider_error" for row in rows), "retry_response_sha256": sha_file(retry_path), "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": len(rows)}
    write_once(ROOT / cfg["outputs"]["retry_audit"], audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
