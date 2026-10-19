"""Execute the frozen P1V4/cau shared semantic plan exactly once per logical ID.

The runner consumes public stories plus internal pair identity mappings only. It
does not read Oracle data, statistical parents, or holdout artifacts.  It has
no automatic transport or validation retry: provider failures are recorded and
the remaining planned logical calls continue independently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import openai
import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fourgraph.semantic_pair_contract_v2 import StablePair  # noqa: E402
from fourgraph.semantic_sentence_id_contract import render_sentence_id_prompt, validate_response_by_pair  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_stage3_shared_semantic_live_authorization_cau.yaml"
AUTH = ROOT / "data/manifests/p1_v4_stage3_shared_semantic_live_execution_authorization_cau.json"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def load(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    value = yaml.safe_load(text) if path.suffix in {".yaml", ".yml"} else json.loads(text)
    if not isinstance(value, dict):
        raise RuntimeError(f"mapping expected: {path}")
    return value


def load_key() -> str:
    value = os.environ.get("OPENAI_API_KEY")
    if value:
        return value
    dot_env = ROOT / ".env"
    if dot_env.is_file():
        for row in dot_env.read_text(encoding="utf-8").splitlines():
            if row.startswith("OPENAI_API_KEY="):
                value = row.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError("OPENAI_API_KEY is missing")


def append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical(value))


def paths(cfg: dict[str, Any]) -> dict[str, Path]:
    root = ROOT / str(cfg["runtime"]["cache_root"])
    return {"root": root, "raw": root / "raw_responses.jsonl", "meta": root / "request_metadata.jsonl",
            "ledger": root / "token_ledger.jsonl", "audit": ROOT / "data/manifests/p1_v4_stage3_shared_semantic_execution_cau_audit.json"}


def verify_auth(cfg: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    auth = load(AUTH)
    if auth.get("status") != "PASS_LIVE_AUTHORIZED" or auth.get("explicit_user_live_authorization") is not True:
        raise RuntimeError("explicit live authorization artifact is missing")
    outputs = cfg["outputs"]
    checkpoint, checkpoint_audit, plan = (ROOT / str(outputs[key]) for key in ("checkpoint", "audit", "execution_plan"))
    if auth.get("checkpoint_sha256") != sha_file(checkpoint) or auth.get("checkpoint_audit_sha256") != sha_file(checkpoint_audit) or auth.get("execution_plan_sha256") != sha_file(plan):
        raise RuntimeError("live authorization pins do not match current frozen artifacts")
    if auth.get("authorized_logical_calls") != 360:
        raise RuntimeError("live authorization workload drift")
    plan_data = load(plan)
    public_manifest = load(ROOT / str(cfg["parents"]["public_story_manifest"]["path"]))
    pool_manifest = load(ROOT / str(cfg["parents"]["condition_pair_pools"]["path"]))
    for name in ("public_story_manifest", "condition_pair_pools"):
        item = cfg["parents"][name]
        if sha_file(ROOT / str(item["path"])) != item["sha256"]:
            raise RuntimeError(f"frozen parent hash drift: {name}")
    if openai.__version__ != "3.6.0" or sys.version.split()[0] != "3.10.21":
        raise RuntimeError("canonical cau SDK/Python version drift")
    return plan_data, public_manifest, pool_manifest


def jobs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    plan, public_manifest, pool_manifest = verify_auth(cfg)
    stories = {(row["study_id"], row["variant"]): row for row in public_manifest["records"]}
    pools = {row["study_id"]: row for row in pool_manifest["records"]}
    schema_hash = cfg["semantic_contract"]["schema_sha256"]
    result: list[dict[str, Any]] = []
    for item in plan["logical_calls"]:
        key = (item["study_id"], item["variant"])
        story_row = stories.get(key); pool = pools.get(item["study_id"])
        if story_row is None or pool is None:
            raise RuntimeError("story or pool missing from frozen plan")
        story_path = ROOT / story_row["artifact_path"]
        story_artifact = load(story_path)
        story = story_artifact.get("builder_input", {}).get("story")
        if not isinstance(story, str) or sha_bytes(story.encode()) != item["story_content_sha256"]:
            raise RuntimeError(f"public story hash drift: {item['logical_id']}")
        if hashlib.sha256(canonical(pool)).hexdigest().upper() != item["pair_pool_sha256"]:
            raise RuntimeError(f"pair pool hash drift: {item['logical_id']}")
        pairs = tuple(StablePair(**pair) for pair in pool["shared_union_pairs"])
        if [pair.pair_id for pair in pairs] != item["pair_ids"] or len(pairs) != item["pair_count"]:
            raise RuntimeError(f"pair identity drift: {item['logical_id']}")
        prompt = render_sentence_id_prompt(prompt_id=item["prompt_id"], story=story, pairs=pairs)
        result.append({**item, "story": story, "pairs": pairs, "prompt": prompt,
                       "prompt_render_sha256": sha_bytes(prompt.encode()), "schema_sha256": schema_hash})
    if len(result) != 360 or len({row["logical_id"] for row in result}) != 360:
        raise RuntimeError("exact semantic plan identity mismatch")
    return result


def existing_by_id(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    results: dict[str, dict[str, Any]] = {}
    for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not text.strip():
            continue
        row = json.loads(text); key = row.get("logical_id")
        if not isinstance(key, str) or key in results:
            raise RuntimeError(f"duplicate/malformed raw cache at line {number}")
        results[key] = row
    return results


def run(execute: bool) -> dict[str, Any]:
    cfg = load(CONFIG)
    items = jobs(cfg)
    io = paths(cfg)
    cached = existing_by_id(io["raw"])
    unknown = set(cached) - {item["logical_id"] for item in items}
    if unknown:
        raise RuntimeError("semantic cache contains unknown logical IDs")
    for row in cached.values():
        if row.get("status") not in {"completed_valid", "completed_pair_invalid", "completed_schema_invalid", "provider_error"}:
            raise RuntimeError("semantic cache status invalid")
    pending = [item for item in items if item["logical_id"] not in cached]
    dry = {"schema_version": "fourgraph.p1_v4_shared_semantic_execution_dry_run.v1", "task": "P1_V4_STAGE_3D_SHARED_SEMANTIC_LIVE_EXECUTION",
           "planned": len(items), "cached": len(cached), "pending": len(pending), "semantic_api_calls": 0,
           "oracle_access": False, "holdout_access": False, "downstream_reasoner": False, "status": "PASS_DRY_RUN"}
    if not execute:
        return dry
    schema_path = ROOT / str(cfg["semantic_contract"]["schema"])
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    client = OpenAI(api_key=load_key(), max_retries=0)
    last_started = 0.0
    for ordinal, item in enumerate(pending, 1):
        pause = 3.15 - (time.perf_counter() - last_started)
        if pause > 0:
            time.sleep(pause)
        started = time.perf_counter(); last_started = started
        try:
            response = client.responses.create(model=item["model_snapshot"], input=item["prompt"], reasoning={"effort": item["reasoning_effort"]},
                max_output_tokens=8192, service_tier="default", store=False,
                text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": schema, "strict": True}},
                metadata={"task": "P1_V4_STAGE_3D_SHARED_SEMANTIC_LIVE_EXECUTION", "logical_id": item["logical_id"], "study_execution": "true"})
            raw_text = response.output_text or ""
            usage = response.usage
            try:
                parsed = json.loads(raw_text)
                validation = validate_response_by_pair(parsed, item["pairs"], item["story"])
                status = "completed_valid" if validation["response_valid"] else "completed_pair_invalid"
            except Exception as exc:
                validation = {"response_valid": False, "pairs": [], "validation_exception": f"{type(exc).__name__}: {exc}"}
                status = "completed_schema_invalid"
            record = {"schema_version": "fourgraph.p1_v4_shared_semantic_raw.v1", "logical_id": item["logical_id"], "ordinal": ordinal,
                      "status": status, "scene_id": item["study_id"], "variant": item["variant"], "prompt_id": item["prompt_id"],
                      "model_snapshot": response.model, "reasoning_effort": item["reasoning_effort"], "request_id": getattr(response, "_request_id", None),
                      "provider_status": response.status, "input_tokens": int(usage.input_tokens), "output_tokens": int(usage.output_tokens),
                      "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0),
                      "total_tokens": int(getattr(usage, "total_tokens", usage.input_tokens + usage.output_tokens)), "latency_ms": round((time.perf_counter() - started) * 1000),
                      "story_content_sha256": item["story_content_sha256"], "pair_pool_sha256": item["pair_pool_sha256"], "prompt_render_sha256": item["prompt_render_sha256"],
                      "response_sha256": sha_bytes(raw_text.encode()), "response_valid": validation["response_valid"],
                      "valid_pair_count": sum(p.get("pair_valid") is True for p in validation.get("pairs", [])), "invalid_pair_count": sum(p.get("pair_valid") is False for p in validation.get("pairs", [])),
                      "raw_text": raw_text}
        except Exception as exc:
            record = {"schema_version": "fourgraph.p1_v4_shared_semantic_raw.v1", "logical_id": item["logical_id"], "ordinal": ordinal,
                      "status": "provider_error", "scene_id": item["study_id"], "variant": item["variant"], "prompt_id": item["prompt_id"],
                      "model_snapshot": item["model_snapshot"], "reasoning_effort": item["reasoning_effort"], "error_type": type(exc).__name__,
                      "error_message": str(exc)[:1000], "latency_ms": round((time.perf_counter() - started) * 1000),
                      "story_content_sha256": item["story_content_sha256"], "pair_pool_sha256": item["pair_pool_sha256"], "prompt_render_sha256": item["prompt_render_sha256"]}
        append(io["raw"], record)
        append(io["meta"], {key: record.get(key) for key in ("logical_id", "status", "scene_id", "variant", "prompt_id", "request_id", "model_snapshot", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "latency_ms", "error_type")})
        append(io["ledger"], {key: record.get(key) for key in ("logical_id", "status", "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens", "request_id")})
        cached[record["logical_id"]] = record
    summary = {"schema_version": "fourgraph.p1_v4_shared_semantic_execution_audit.v1", "task": "P1_V4_STAGE_3D_SHARED_SEMANTIC_LIVE_EXECUTION",
               "planned_logical_calls": len(items), "recorded_logical_calls": len(cached),
               "counts_by_status": {status: sum(row.get("status") == status for row in cached.values()) for status in ("completed_valid", "completed_pair_invalid", "completed_schema_invalid", "provider_error")},
               "provider_usage": {key: sum(int(row.get(key, 0) or 0) for row in cached.values()) for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")},
               "raw_response_sha256": sha_file(io["raw"]), "request_metadata_sha256": sha_file(io["meta"]), "token_ledger_sha256": sha_file(io["ledger"]),
               "oracle_access": 0, "holdout_access": 0, "downstream_reasoner": 0,
               "status": "PASS" if len(cached) == len(items) and not any(row.get("status") == "provider_error" for row in cached.values()) else "INCOMPLETE_OR_PROVIDER_INCIDENT"}
    io["audit"].parent.mkdir(parents=True, exist_ok=True); io["audit"].write_bytes(canonical(summary))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(); result = run(execute=args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] in {"PASS_DRY_RUN", "PASS"} else 1)
