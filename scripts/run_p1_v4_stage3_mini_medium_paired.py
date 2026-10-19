"""Run the frozen Mini-medium paired comparator, one cacheable call per logical ID."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import openai
import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from fourgraph.semantic_pair_contract_v2 import StablePair  # noqa: E402
from fourgraph.semantic_sentence_id_contract import render_sentence_id_prompt, validate_response_by_pair  # noqa: E402
from run_p1_v4_stage3_shared_semantic_cau import load_key  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_stage3_mini_medium_paired_comparator.yaml"
AUTH = ROOT / "data/manifests/p1_v4_stage3_mini_medium_paired_live_authorization.json"


def canonical(value: Any) -> bytes: return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
def sha(value: bytes) -> str: return hashlib.sha256(value).hexdigest().upper()
def sha_file(path: Path) -> str: return sha(path.read_bytes())
def load(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8"); value = yaml.safe_load(text) if path.suffix in {".yaml", ".yml"} else json.loads(text)
    if not isinstance(value, dict): raise RuntimeError(f"mapping expected: {path}")
    return value
def append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle: handle.write(canonical(value))


def jobs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    auth = load(AUTH); plan_path = ROOT / cfg["outputs"]["paired_execution_plan"]
    if auth.get("status") != "PASS_LIVE_AUTHORIZED" or auth.get("execution_plan_sha256") != sha_file(plan_path) or auth.get("authorized_logical_calls") != 360:
        raise RuntimeError("Mini live authorization does not pin the frozen exact plan")
    plan = load(plan_path); public = load(ROOT / cfg["parents"]["public_story_manifest"]["path"]); pools = load(ROOT / cfg["parents"]["condition_pair_pools"]["path"])
    stories = {(row["study_id"], row["variant"]): row for row in public["records"]}; by_scene = {row["study_id"]: row for row in pools["records"]}
    out: list[dict[str, Any]] = []
    for item in plan["logical_calls"]:
        story_row, pool = stories.get((item["study_id"], item["variant"])), by_scene.get(item["study_id"])
        if story_row is None or pool is None: raise RuntimeError("missing frozen story/pair pool")
        story = load(ROOT / story_row["artifact_path"])["builder_input"]["story"]
        if sha(story.encode()) != item["story_content_sha256"] or sha(canonical(pool)) != item["pair_pool_sha256"]: raise RuntimeError("frozen input hash drift")
        pairs = tuple(StablePair(**row) for row in pool["shared_union_pairs"])
        if [pair.pair_id for pair in pairs] != item["pair_ids"]: raise RuntimeError("pair identity drift")
        prompt = render_sentence_id_prompt(prompt_id=item["prompt_id"], story=story, pairs=pairs)
        out.append({**item, "story": story, "pairs": pairs, "prompt": prompt, "prompt_render_sha256": sha(prompt.encode())})
    if len(out) != 360 or len({row["logical_id"] for row in out}) != 360: raise RuntimeError("Mini jobs are not exactly 360 unique ids")
    return out


def existing(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists(): return {}
    result: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip(): continue
        row = json.loads(line); logical_id = row.get("logical_id")
        if not isinstance(logical_id, str) or logical_id in result: raise RuntimeError(f"duplicate/malformed Mini cache at line {line_no}")
        result[logical_id] = row
    return result


def run(execute: bool) -> dict[str, Any]:
    cfg = load(CONFIG); items = jobs(cfg); root = ROOT / cfg["execution"]["cache_root"]
    raw, meta, ledger = root / "raw_responses.jsonl", root / "request_metadata.jsonl", root / "token_ledger.jsonl"; cached = existing(raw)
    if set(cached) - {row["logical_id"] for row in items}: raise RuntimeError("Mini cache includes unknown logical id")
    pending = [row for row in items if row["logical_id"] not in cached]
    dry = {"task": "P1_V4_STAGE_3D_MINI_MEDIUM_PAIRED_LIVE_EXECUTION", "status": "PASS_DRY_RUN", "planned": 360, "cached": len(cached), "pending": len(pending), "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0}
    if not execute: return dry
    if sys.version.split()[0] != "3.10.21" or openai.__version__ != "3.6.0": raise RuntimeError("canonical cau version drift")
    schema = json.loads((ROOT / "schemas/semantic_sentence_id_response_v1.schema.json").read_text(encoding="utf-8")); client = OpenAI(api_key=load_key(), max_retries=0, timeout=120); last = 0.0
    for ordinal, item in enumerate(pending, 1):
        pause = 3.15 - (time.perf_counter() - last)
        if pause > 0: time.sleep(pause)
        began = time.perf_counter(); last = began
        try:
            response = client.responses.create(model=item["model_snapshot"], input=item["prompt"], reasoning={"effort": item["reasoning_effort"]}, max_output_tokens=cfg["execution"]["max_output_tokens"], service_tier="default", store=False,
                text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": schema, "strict": True}}, metadata={"task": "P1_V4_STAGE_3D_MINI_MEDIUM_PAIRED_LIVE_EXECUTION", "logical_id": item["logical_id"]})
            raw_text, usage = response.output_text or "", response.usage
            try:
                validation = validate_response_by_pair(json.loads(raw_text), item["pairs"], item["story"]); status = "completed_valid" if validation["response_valid"] else "completed_pair_invalid"
            except Exception as exc:
                validation = {"response_valid": False, "pairs": [], "validation_exception": f"{type(exc).__name__}: {exc}"}; status = "completed_schema_invalid"
            record = {"schema_version": "fourgraph.p1_v4_mini_medium_paired_raw.v1", "logical_id": item["logical_id"], "ordinal": ordinal, "status": status, "scene_id": item["study_id"], "variant": item["variant"], "prompt_id": item["prompt_id"], "model_snapshot": response.model, "reasoning_effort": item["reasoning_effort"], "request_id": getattr(response, "_request_id", None), "provider_status": response.status, "input_tokens": int(usage.input_tokens), "output_tokens": int(usage.output_tokens), "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0), "total_tokens": int(getattr(usage, "total_tokens", usage.input_tokens + usage.output_tokens)), "latency_ms": round((time.perf_counter()-began)*1000), "story_content_sha256": item["story_content_sha256"], "pair_pool_sha256": item["pair_pool_sha256"], "prompt_render_sha256": item["prompt_render_sha256"], "response_sha256": sha(raw_text.encode()), "response_valid": validation["response_valid"], "valid_pair_count": sum(p.get("pair_valid") is True for p in validation.get("pairs", [])), "invalid_pair_count": sum(p.get("pair_valid") is False for p in validation.get("pairs", [])), "raw_text": raw_text}
        except Exception as exc:
            record = {"schema_version": "fourgraph.p1_v4_mini_medium_paired_raw.v1", "logical_id": item["logical_id"], "ordinal": ordinal, "status": "provider_error", "scene_id": item["study_id"], "variant": item["variant"], "prompt_id": item["prompt_id"], "model_snapshot": item["model_snapshot"], "reasoning_effort": item["reasoning_effort"], "error_type": type(exc).__name__, "error_message": str(exc)[:1000], "latency_ms": round((time.perf_counter()-began)*1000), "story_content_sha256": item["story_content_sha256"], "pair_pool_sha256": item["pair_pool_sha256"], "prompt_render_sha256": item["prompt_render_sha256"]}
        append(raw, record); append(meta, {key: record.get(key) for key in ("logical_id", "status", "scene_id", "variant", "prompt_id", "request_id", "model_snapshot", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "latency_ms", "error_type")}); append(ledger, {key: record.get(key) for key in ("logical_id", "status", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "request_id")}); cached[record["logical_id"]] = record
    statuses = ("completed_valid", "completed_pair_invalid", "completed_schema_invalid", "provider_error")
    result = {"schema_version": "fourgraph.p1_v4_mini_medium_paired_execution_audit.v1", "task": "P1_V4_STAGE_3D_MINI_MEDIUM_PAIRED_LIVE_EXECUTION", "planned_logical_calls": 360, "recorded_logical_calls": len(cached), "counts_by_status": {status: sum(row.get("status") == status for row in cached.values()) for status in statuses}, "provider_usage": {key: sum(int(row.get(key, 0) or 0) for row in cached.values()) for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")}, "raw_response_sha256": sha_file(raw), "request_metadata_sha256": sha_file(meta), "token_ledger_sha256": sha_file(ledger), "oracle_access": 0, "holdout_access": 0, "metrics": 0, "status": "PASS" if len(cached) == 360 and not any(row.get("status") == "provider_error" for row in cached.values()) else "INCOMPLETE_OR_PROVIDER_INCIDENT"}
    audit_path = ROOT / "data/manifests/p1_v4_stage3_mini_medium_paired_execution_audit.json"; audit_path.write_bytes(canonical(result)); return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); args = parser.parse_args(); result = run(args.execute); print(json.dumps(result, ensure_ascii=False, indent=2)); raise SystemExit(0 if result["status"] in {"PASS_DRY_RUN", "PASS"} else 1)
