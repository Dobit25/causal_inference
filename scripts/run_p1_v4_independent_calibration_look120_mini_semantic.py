"""Run the frozen Mini look-120 plan; no call occurs without a live artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import os
import sys
import time
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import openai
import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.semantic_pair_contract_v2 import StablePair  # noqa: E402
from fourgraph.semantic_sentence_id_contract import render_sentence_id_prompt, validate_response_by_pair  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_mini_semantic_live_authorization.yaml"

def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest().upper()

def load(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    value = yaml.safe_load(text) if path.suffix in {".yaml", ".yml"} else json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError(f"mapping expected: {path}")
    return value

def append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical(row))

def load_key() -> str:
    value = os.environ.get("OPENAI_API_KEY")
    if value:
        return value
    dot_env = ROOT / ".env"
    if dot_env.is_file():
        for line in dot_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError("OPENAI_API_KEY is missing")


class ExternalWatchdogTimeout(RuntimeError):
    """A request worker did not finish before the separately frozen deadline."""


class ExternalWatchdogWorkerError(RuntimeError):
    """The one-shot worker returned an API or worker error."""


def _watchdog_worker(
    send_connection: Any,
    model: str,
    prompt: str,
    reasoning_effort: str,
    schema: dict[str, Any],
    attempt_timeout_seconds: float,
) -> None:
    """Perform exactly one provider attempt in an isolated child process."""
    try:
        client = OpenAI(api_key=load_key(), max_retries=0, timeout=attempt_timeout_seconds)
        response = client.responses.create(
            model=model,
            input=prompt,
            reasoning={"effort": reasoning_effort},
            max_output_tokens=8192,
            service_tier="default",
            store=False,
            text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": schema, "strict": True}},
        )
        usage = response.usage
        send_connection.send({
            "ok": True,
            "model": response.model,
            "request_id": getattr(response, "_request_id", None),
            "raw_text": response.output_text or "",
            "input_tokens": int(usage.input_tokens),
            "output_tokens": int(usage.output_tokens),
            "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0),
            "total_tokens": getattr(usage, "total_tokens", None),
        })
    except BaseException as exc:
        send_connection.send({"ok": False, "error_type": type(exc).__name__, "error_message": str(exc)[:1000]})
    finally:
        send_connection.close()


def watchdog_response(job: dict[str, Any], schema: dict[str, Any], watchdog: dict[str, Any]) -> dict[str, Any]:
    """Run one isolated API attempt; a parent-enforced deadline terminates only that worker."""
    timeout = float(watchdog["worker_deadline_seconds"])
    attempt_timeout = float(watchdog["sdk_attempt_timeout_seconds"])
    if not 1 <= attempt_timeout < timeout <= 600:
        raise RuntimeError("malformed external watchdog timeouts")
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    worker = context.Process(
        target=_watchdog_worker,
        args=(send_connection, job["model"], job["prompt"], job["reasoning_effort"], schema, attempt_timeout),
    )
    worker.start()
    send_connection.close()
    if not receive_connection.poll(timeout):
        worker.terminate()
        worker.join(timeout=15)
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=15)
        receive_connection.close()
        raise ExternalWatchdogTimeout(f"worker exceeded {timeout:g}s deadline")
    result = receive_connection.recv()
    receive_connection.close()
    worker.join(timeout=15)
    if worker.is_alive():
        worker.terminate()
        worker.join(timeout=15)
    if not isinstance(result, dict) or result.get("ok") is not True:
        error_type = result.get("error_type", "ExternalWatchdogWorkerError") if isinstance(result, dict) else "ExternalWatchdogWorkerError"
        error_message = result.get("error_message", "worker returned no result") if isinstance(result, dict) else "worker returned malformed result"
        raise ExternalWatchdogWorkerError(f"{error_type}: {error_message}")
    if not isinstance(result.get("total_tokens"), int):
        raise RuntimeError("missing provider-reported total_tokens")
    return result

def io_paths(cfg: dict[str, Any]) -> dict[str, Path]:
    base = ROOT / cfg["runtime"]["cache_root"]
    return {"raw": base / "raw_responses.jsonl", "metadata": base / "request_metadata.jsonl", "ledger": base / "token_ledger.jsonl", "audit": ROOT / cfg["outputs"]["runner_audit"]}

def existing(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line); logical_id = row.get("logical_id")
        if not isinstance(logical_id, str) or logical_id in rows:
            raise RuntimeError(f"duplicate/malformed cache at line {index}")
        rows[logical_id] = row
    return rows

def apply_transport_retry_overlay(cfg: dict[str, Any], rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Overlay separately authorized successful retries without mutating historical errors."""
    overlay = cfg.get("runtime", {}).get("transport_retry_overlay")
    if overlay is None:
        return rows
    if not isinstance(overlay, dict) or not isinstance(overlay.get("path"), str) or not isinstance(overlay.get("sha256"), str):
        raise RuntimeError("malformed transport retry overlay")
    path = ROOT / overlay["path"]
    if not path.is_file() or sha_file(path) != overlay["sha256"]:
        raise RuntimeError("transport retry overlay hash drift")
    retry_rows = existing(path)
    for logical_id, retry in retry_rows.items():
        prior = rows.get(logical_id)
        if prior is None or prior.get("status") != "provider_error":
            raise RuntimeError("retry overlay does not replace a historical provider error")
        if retry.get("status") == "provider_error" or retry.get("retry_of_status") != "provider_error":
            raise RuntimeError("unresolved/malformed transport retry overlay")
        rows[logical_id] = retry
    return rows

def window_start(now: datetime) -> datetime:
    local = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    boundary = datetime.combine(local.date(), dtime(7, 0), tzinfo=local.tzinfo)
    return boundary if local >= boundary else boundary - timedelta(days=1)

def build_jobs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    plan_path = ROOT / cfg["parents"]["execution_plan"]["path"]
    if sha_file(plan_path) != cfg["parents"]["execution_plan"]["sha256"]:
        raise RuntimeError("execution plan hash drift")
    plan = load(plan_path); pools = plan["pair_pools"]
    jobs: list[dict[str, Any]] = []
    for item in plan["logical_calls"]:
        pool = pools[item["study_id"]]
        pair_rows = pool["pairs"]
        pairs = tuple(StablePair(pair_id=row["pair_id"], node_a_alias=row["node_a_alias"], node_b_alias=row["node_b_alias"], node_a_id=row["node_a_canonical"], node_b_id=row["node_b_canonical"]) for row in pair_rows)
        story_artifact = load(ROOT / item["story_artifact_path"])
        story = story_artifact.get("builder_input", {}).get("story")
        if not isinstance(story, str) or sha_text(story) != item["story_content_sha256"]:
            raise RuntimeError(f"story hash drift: {item['logical_id']}")
        prompt = render_sentence_id_prompt(prompt_id=item["prompt_id"], story=story, pairs=pairs)
        jobs.append({**item, "pairs": pairs, "story": story, "prompt": prompt, "prompt_render_sha256": sha_text(prompt)})
    if len(jobs) != cfg["scope"]["logical_calls"] or len({job["logical_id"] for job in jobs}) != len(jobs):
        raise RuntimeError("logical call identity mismatch")
    if not all(job["model"] == cfg["semantic_contract"]["model"] and job["reasoning_effort"] == cfg["semantic_contract"]["reasoning_effort"] for job in jobs):
        raise RuntimeError("Mini model/effort drift")
    return jobs

def verify_live_auth(cfg: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / cfg["outputs"]["live_authorization"]
    if not path.is_file():
        raise RuntimeError("live authorization artifact missing")
    auth = load(path)
    checkpoint = ROOT / cfg["outputs"]["live_authorization_checkpoint"]
    if auth.get("status") != "PASS_LIVE_AUTHORIZED" or auth.get("explicit_user_live_authorization") is not True:
        raise RuntimeError("explicit live authorization absent")
    if auth.get("checkpoint_sha256") != sha_file(checkpoint) or auth.get("authorized_logical_calls") != cfg["scope"]["logical_calls"]:
        raise RuntimeError("live authorization pin/workload mismatch")
    return auth

def current_window_tokens(ledger: Path) -> int:
    if not ledger.exists():
        return 0
    start = window_start(datetime.now(tz=ZoneInfo("Asia/Ho_Chi_Minh"))).isoformat()
    total = 0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("window_start") == start:
            tokens = row.get("total_tokens")
            if not isinstance(tokens, int):
                raise RuntimeError("missing provider usage in existing ledger")
            total += tokens
    return total

def run(execute: bool, config_path: Path = CONFIG, max_new_calls: int | None = None) -> dict[str, Any]:
    cfg = load(config_path); jobs = build_jobs(cfg); io = io_paths(cfg); cached = apply_transport_retry_overlay(cfg, existing(io["raw"]))
    if set(cached) - {job["logical_id"] for job in jobs}:
        raise RuntimeError("unknown logical ID in cache")
    pending = [job for job in jobs if job["logical_id"] not in cached]
    dry = {"task": cfg["task"], "status": "PASS_DRY_RUN", "planned_logical_calls": len(jobs), "cached": len(cached), "pending": len(pending), "study_api_calls": 0, "oracle_access": 0, "holdout_access": 0}
    if not execute:
        return dry
    auth = verify_live_auth(cfg)
    cap = int(auth["execution_slice"]["max_new_calls"])
    if max_new_calls is not None:
        if max_new_calls < 1 or max_new_calls > cap:
            raise RuntimeError("requested execution slice exceeds explicit authorization")
        cap = max_new_calls
    authorized_ids = auth.get("execution_slice", {}).get("authorized_pending_logical_ids")
    if authorized_ids is not None:
        if not isinstance(authorized_ids, list) or any(not isinstance(item, str) for item in authorized_ids):
            raise RuntimeError("malformed pinned authorization identities")
        if len(authorized_ids) != cap or [job["logical_id"] for job in pending[:cap]] != authorized_ids:
            raise RuntimeError("pending IDs do not match the separately authorized execution slice")
    scheduled = pending[:cap]
    schema = json.loads((ROOT / cfg["semantic_contract"]["schema"]).read_text(encoding="utf-8"))
    watchdog = cfg.get("runtime", {}).get("external_watchdog")
    if watchdog is not None and (not isinstance(watchdog, dict) or watchdog.get("enabled") is not True):
        raise RuntimeError("external_watchdog must be an enabled mapping when configured")
    client_kwargs: dict[str, Any] = {"api_key": load_key(), "max_retries": 0}
    request_timeout_seconds = cfg.get("runtime", {}).get("request_timeout_seconds")
    if request_timeout_seconds is not None:
        if not isinstance(request_timeout_seconds, (int, float)) or not 1 <= float(request_timeout_seconds) <= 600:
            raise RuntimeError("request_timeout_seconds must be between 1 and 600")
        client_kwargs["timeout"] = float(request_timeout_seconds)
    client = OpenAI(**client_kwargs)
    used = current_window_tokens(io["ledger"]); limit = int(cfg["token_control"]["hard_stop_tokens"]); batch_size = int(cfg["runtime"]["batch_size"])
    minimum_interval = float(cfg["runtime"]["minimum_request_interval_seconds"])
    last_started = 0.0
    for position, job in enumerate(scheduled, 1):
        pause = minimum_interval - (time.perf_counter() - last_started)
        if pause > 0:
            time.sleep(pause)
        started = time.perf_counter()
        last_started = started
        try:
            if watchdog is None:
                response = client.responses.create(model=job["model"], input=job["prompt"], reasoning={"effort": job["reasoning_effort"]}, max_output_tokens=8192, service_tier="default", store=False, text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": schema, "strict": True}}, metadata={"task": cfg["task"], "logical_id": job["logical_id"], "study_execution": "true"})
                usage = response.usage
                total = getattr(usage, "total_tokens", None)
                if not isinstance(total, int):
                    raise RuntimeError("missing provider-reported total_tokens")
                response_fields = {"model": response.model, "request_id": getattr(response, "_request_id", None), "raw_text": response.output_text or "", "input_tokens": int(usage.input_tokens), "output_tokens": int(usage.output_tokens), "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0), "total_tokens": total}
            else:
                response_fields = watchdog_response(job, schema, watchdog)
            raw_text = response_fields["raw_text"]
            try:
                validation = validate_response_by_pair(json.loads(raw_text), job["pairs"], job["story"])
                status = "completed_valid" if validation["response_valid"] else "completed_pair_invalid"
            except Exception as exc:
                validation = {"response_valid": False, "pairs": [], "validation_exception": f"{type(exc).__name__}: {exc}"}; status = "completed_schema_invalid"
            record = {"logical_id": job["logical_id"], "status": status, "scene_id": job["study_id"], "variant": job["variant"], "prompt_id": job["prompt_id"], "model": response_fields["model"], "reasoning_effort": job["reasoning_effort"], "request_id": response_fields["request_id"], "input_tokens": response_fields["input_tokens"], "output_tokens": response_fields["output_tokens"], "reasoning_tokens": response_fields["reasoning_tokens"], "total_tokens": response_fields["total_tokens"], "latency_ms": round((time.perf_counter()-started)*1000), "response_sha256": sha_text(raw_text), "story_content_sha256": job["story_content_sha256"], "pair_pool_sha256": job["pair_pool_sha256"], "prompt_render_sha256": job["prompt_render_sha256"], "raw_text": raw_text, "response_valid": validation["response_valid"], "valid_pair_count": sum(row.get("pair_valid") is True for row in validation.get("pairs", [])), "invalid_pair_count": sum(row.get("pair_valid") is False for row in validation.get("pairs", [])), "external_watchdog": watchdog is not None}
        except Exception as exc:
            record = {"logical_id": job["logical_id"], "status": "provider_error", "scene_id": job["study_id"], "variant": job["variant"], "prompt_id": job["prompt_id"], "model": job["model"], "reasoning_effort": job["reasoning_effort"], "error_type": type(exc).__name__, "error_message": str(exc)[:1000], "latency_ms": round((time.perf_counter()-started)*1000), "story_content_sha256": job["story_content_sha256"], "pair_pool_sha256": job["pair_pool_sha256"], "prompt_render_sha256": job["prompt_render_sha256"]}
        append(io["raw"], record); append(io["metadata"], {key: record.get(key) for key in ("logical_id", "status", "scene_id", "variant", "prompt_id", "model", "request_id", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "error_type")})
        if record["status"] != "provider_error":
            window = window_start(datetime.now(tz=ZoneInfo("Asia/Ho_Chi_Minh"))).isoformat(); used += record["total_tokens"]
            append(io["ledger"], {"window_start": window, "logical_id": record["logical_id"], "input_tokens": record["input_tokens"], "output_tokens": record["output_tokens"], "reasoning_tokens": record["reasoning_tokens"], "total_tokens": record["total_tokens"], "remaining_tokens_after_call": max(0, limit-used), "cost_usd": None})
        cached[record["logical_id"]] = record
        if position % batch_size == 0 and used >= limit:
            break
    provider_errors = any(row.get("status") == "provider_error" for row in cached.values())
    if provider_errors:
        status = "INCOMPLETE_OR_PROVIDER_INCIDENT"
    elif len(cached) == len(jobs):
        status = "PASS"
    else:
        status = "AUTHORIZED_SLICE_COMPLETE"
    summary = {"task": cfg["task"], "planned_logical_calls": len(jobs), "scheduled_this_run": len(scheduled), "recorded_logical_calls": len(cached), "provider_usage": {key: sum(int(row.get(key, 0) or 0) for row in cached.values()) for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")}, "token_window_used": used, "token_hard_stop": limit, "oracle_access": 0, "holdout_access": 0, "status": status}
    io["audit"].parent.mkdir(parents=True, exist_ok=True); io["audit"].write_bytes(canonical(summary)); return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); parser.add_argument("--config", type=Path, default=CONFIG); parser.add_argument("--max-new-calls", type=int)
    args = parser.parse_args(); result = run(args.execute, args.config, args.max_new_calls); print(json.dumps(result, indent=2)); raise SystemExit(0 if result["status"] in {"PASS", "PASS_DRY_RUN", "AUTHORIZED_SLICE_COMPLETE"} else 1)
