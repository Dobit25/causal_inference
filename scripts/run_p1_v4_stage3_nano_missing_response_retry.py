"""Execute the one separately-authorized Nano retry without rewriting history."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fourgraph.semantic_pair_contract_v2 import StablePair  # noqa: E402
from fourgraph.semantic_sentence_id_contract import render_sentence_id_prompt, validate_response_by_pair  # noqa: E402
from run_p1_v4_stage3_shared_semantic_cau import load_key  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_stage3_nano_missing_response_retry_amendment.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    value = yaml.safe_load(text) if path.suffix in {".yaml", ".yml"} else json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError(f"mapping expected: {path}")
    return value


def append(path: Path, value: dict[str, Any]) -> None:
    with path.open("ab") as handle:
        handle.write(canonical(value))


def build_target(cfg: dict[str, Any]) -> dict[str, Any]:
    plan_path = ROOT / cfg["parent_execution"]["execution_plan"]
    if sha(plan_path) != cfg["parent_execution"]["execution_plan_sha256"]:
        raise RuntimeError("execution plan hash drift")
    raw = ROOT / cfg["parent_execution"]["raw_responses"]
    if sha(raw) != cfg["parent_execution"]["raw_responses_sha256_before_retry"]:
        raise RuntimeError("raw history hash drift; retry amendment no longer applies")
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    target_id = cfg["retry_scope"]["logical_id"]
    target_rows = [row for row in rows if row.get("logical_id") == target_id]
    if len(target_rows) != 1 or target_rows[0].get("status") != "provider_error" or target_rows[0].get("error_type") != "TransportOutcomeUnknown":
        raise RuntimeError("target is not the uniquely recorded transport-outcome-unknown call")
    plan = load(plan_path)
    item = next((row for row in plan["logical_calls"] if row["logical_id"] == target_id), None)
    if item is None:
        raise RuntimeError("target not in frozen plan")
    public = load(ROOT / "data/manifests/p1_v4_stage3_public_semantic_inputs_cau.json")
    pools = load(ROOT / "data/manifests/p1_v4_stage3_condition_pair_pools_cau.json")
    story_row = next((row for row in public["records"] if row["study_id"] == item["study_id"] and row["variant"] == item["variant"]), None)
    pool = next((row for row in pools["records"] if row["study_id"] == item["study_id"]), None)
    if story_row is None or pool is None:
        raise RuntimeError("frozen story/pair pool missing")
    story_artifact = load(ROOT / story_row["artifact_path"])
    story = story_artifact["builder_input"]["story"]
    if hashlib.sha256(story.encode()).hexdigest().upper() != item["story_content_sha256"]:
        raise RuntimeError("story-content hash drift")
    pool_hash = hashlib.sha256(canonical(pool)).hexdigest().upper()
    if pool_hash != item["pair_pool_sha256"]:
        raise RuntimeError("pair-pool hash drift")
    pairs = tuple(StablePair(**pair) for pair in pool["shared_union_pairs"])
    if [pair.pair_id for pair in pairs] != item["pair_ids"]:
        raise RuntimeError("pair identity drift")
    prompt = render_sentence_id_prompt(prompt_id=item["prompt_id"], story=story, pairs=pairs)
    return {**item, "story": story, "pairs": pairs, "prompt": prompt, "raw_path": raw,
            "meta_path": raw.parent / "request_metadata.jsonl", "ledger_path": raw.parent / "token_ledger.jsonl"}


def run(execute: bool) -> dict[str, Any]:
    cfg = load(CONFIG)
    target = build_target(cfg)
    preview = {"task": cfg["task"], "status": "PASS_DRY_RUN", "target": target["logical_id"],
               "new_provider_calls": 0, "oracle_access": 0, "holdout_access": 0, "metrics": 0}
    if not execute:
        return preview
    schema = json.loads((ROOT / "schemas/semantic_sentence_id_response_v1.schema.json").read_text(encoding="utf-8"))
    started = time.perf_counter()
    try:
        client = OpenAI(api_key=load_key(), max_retries=0, timeout=cfg["retry_scope"]["timeout_seconds"])
        response = client.responses.create(
            model=target["model_snapshot"], input=target["prompt"], reasoning={"effort": target["reasoning_effort"]},
            max_output_tokens=8192, service_tier="default", store=False,
            text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": schema, "strict": True}},
            metadata={"task": cfg["task"], "logical_id": target["logical_id"], "retry_attempt": "1"},
        )
        raw_text = response.output_text or ""
        usage = response.usage
        try:
            validation = validate_response_by_pair(json.loads(raw_text), target["pairs"], target["story"])
            status = "completed_valid" if validation["response_valid"] else "completed_pair_invalid"
        except Exception as exc:
            validation = {"response_valid": False, "pairs": [], "validation_exception": f"{type(exc).__name__}: {exc}"}
            status = "completed_schema_invalid"
        record = {"schema_version": "fourgraph.p1_v4_shared_semantic_raw.v1", "logical_id": target["logical_id"], "attempt": 1,
                  "retry_of_status": "provider_error", "status": status, "scene_id": target["study_id"], "variant": target["variant"],
                  "prompt_id": target["prompt_id"], "model_snapshot": response.model, "reasoning_effort": target["reasoning_effort"],
                  "request_id": getattr(response, "_request_id", None), "provider_status": response.status,
                  "input_tokens": int(usage.input_tokens), "output_tokens": int(usage.output_tokens),
                  "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0),
                  "total_tokens": int(getattr(usage, "total_tokens", usage.input_tokens + usage.output_tokens)),
                  "latency_ms": round((time.perf_counter() - started) * 1000),
                  "story_content_sha256": target["story_content_sha256"], "pair_pool_sha256": target["pair_pool_sha256"],
                  "prompt_render_sha256": hashlib.sha256(target["prompt"].encode()).hexdigest().upper(),
                  "response_sha256": hashlib.sha256(raw_text.encode()).hexdigest().upper(), "response_valid": validation["response_valid"],
                  "valid_pair_count": sum(p.get("pair_valid") is True for p in validation.get("pairs", [])),
                  "invalid_pair_count": sum(p.get("pair_valid") is False for p in validation.get("pairs", [])), "raw_text": raw_text}
    except Exception as exc:
        record = {"schema_version": "fourgraph.p1_v4_shared_semantic_raw.v1", "logical_id": target["logical_id"], "attempt": 1,
                  "retry_of_status": "provider_error", "status": "provider_error", "scene_id": target["study_id"], "variant": target["variant"],
                  "prompt_id": target["prompt_id"], "model_snapshot": target["model_snapshot"], "reasoning_effort": target["reasoning_effort"],
                  "error_type": type(exc).__name__, "error_message": str(exc)[:1000], "latency_ms": round((time.perf_counter() - started) * 1000),
                  "story_content_sha256": target["story_content_sha256"], "pair_pool_sha256": target["pair_pool_sha256"],
                  "prompt_render_sha256": hashlib.sha256(target["prompt"].encode()).hexdigest().upper()}
    append(target["raw_path"], record)
    append(target["meta_path"], {key: record.get(key) for key in ("logical_id", "attempt", "status", "scene_id", "variant", "prompt_id", "request_id", "model_snapshot", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "latency_ms", "error_type")})
    append(target["ledger_path"], {key: record.get(key) for key in ("logical_id", "attempt", "status", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "request_id")})
    audit = {"schema_version": "fourgraph.p1_v4_stage3_nano_missing_response_retry_execution_audit.v1", "task": cfg["task"],
             "target": target["logical_id"], "allowed_new_provider_calls": 1, "attempt": 1, "result_status": record["status"],
             "request_id": record.get("request_id"), "provider_usage": {key: record.get(key) for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")},
             "raw_history_sha256_after_retry": sha(target["raw_path"]), "oracle_access": 0, "holdout_access": 0, "metrics": 0,
             "status": "PASS_RESPONSE_RECEIVED" if record["status"] != "provider_error" else "FAIL_PROVIDER_RETRY"}
    (ROOT / cfg["outputs"]["execution_audit"]).write_bytes(canonical(audit))
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); args = parser.parse_args()
    result = run(args.execute); print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] in {"PASS_DRY_RUN", "PASS_RESPONSE_RECEIVED"} else 1)
