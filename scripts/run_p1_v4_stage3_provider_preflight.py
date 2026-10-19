"""Run exactly one non-study provider preflight for the frozen P1V4 contract."""

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
DEFAULT_CONFIG = ROOT / "configs/p1_v4_stage3_provider_preflight.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENAI_API_KEY is missing")


def dependency(path_text: str, expected: str | None = None) -> dict[str, str]:
    path = ROOT / path_text
    if not path.is_file():
        raise RuntimeError(f"missing dependency: {path_text}")
    actual = sha_file(path)
    if expected and actual != expected:
        raise RuntimeError(f"hash drift for {path_text}: {actual} != {expected}")
    return {"path": path_text, "sha256": actual}


def build_prompt(prompt_path: Path) -> str:
    aliases = [
        "Amber index", "Beryl index", "Cobalt index", "Dahlia index",
        "Ember index", "Fallow index", "Grove index",
    ]
    sentences = [
        "This synthetic preflight story contains seven measured quantities: " + ", ".join(aliases) + ".",
        "Changes in Amber index directly influence Beryl index.",
        "Changes in Beryl index directly influence Cobalt index.",
        "Changes in Cobalt index directly influence Dahlia index.",
        "Changes in Dahlia index directly influence Ember index.",
        "Changes in Ember index directly influence Fallow index.",
        "Changes in Fallow index directly influence Grove index.",
    ]
    numbered = "\n".join(f"[S{index:03d}] {sentence}" for index, sentence in enumerate(sentences, 1))
    pairs = []
    pair_number = 1
    for index, left in enumerate(aliases):
        for right in aliases[index + 1:]:
            pairs.append({"pair_id": f"pair_{pair_number:02d}", "node_a_alias": left, "node_b_alias": right})
            pair_number += 1
    return (
        prompt_path.read_text(encoding="utf-8")
        + "\n\nQUERY VARIANT P1:\nInspect node_a before node_b and identify direct cause/effect evidence.\n\n"
        + "NUMBERED PUBLIC STORY:\n" + numbered
        + "\n\nSTABLE REQUESTED PAIRS:\n"
        + json.dumps(pairs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def validate_response(raw_text: str, expected_pair_count: int) -> None:
    parsed = json.loads(raw_text)
    if parsed.get("schema_version") != "fourgraph.semantic_sentence_id_response.v1":
        raise RuntimeError("response schema_version mismatch")
    judgments = parsed.get("judgments")
    if not isinstance(judgments, list) or len(judgments) != expected_pair_count:
        raise RuntimeError("response does not contain exactly 21 judgments")
    pair_ids = [row.get("pair_id") for row in judgments]
    if len(set(pair_ids)) != expected_pair_count or any(not item for item in pair_ids):
        raise RuntimeError("response pair_id coverage is not one-to-one")


def run(config_path: Path, execute: bool) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    contract = config["semantic_contract"]
    output_path = ROOT / config["outputs"]["provider_preflight"]
    dependencies = {
        "config": {"path": str(config_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha_file(config_path)},
        "semantic_protocol": dependency(config["parents"]["semantic_protocol"]["path"], config["parents"]["semantic_protocol"]["sha256"]),
        "statistical_execution_audit": dependency(config["parents"]["statistical_execution_audit"]["path"], config["parents"]["statistical_execution_audit"]["sha256"]),
        "environment_lock": dependency(config["parents"]["environment_lock"]["path"]),
        "prompt": dependency(contract["prompt"]),
        "schema": dependency(contract["schema"]),
    }
    parent = json.loads((ROOT / config["parents"]["statistical_execution_audit"]["path"]).read_text(encoding="utf-8"))
    boundary = parent.get("execution_boundary", {})
    if parent.get("status") != "PASS_STATISTICAL_EXECUTION" or boundary.get("semantic_api_calls") != 0:
        raise RuntimeError("statistical execution boundary is not eligible for provider preflight")
    if boundary.get("oracle_access") or boundary.get("holdout_access"):
        raise RuntimeError("statistical execution boundary has forbidden access")
    if openai.__version__ != "3.6.0":
        raise RuntimeError(f"pinned OpenAI SDK drift: expected 3.6.0, got {openai.__version__}")
    prompt = build_prompt(ROOT / contract["prompt"])
    base = {
        "schema_version": "fourgraph.p1_v4_stage3_provider_preflight.v1",
        "task": config["task"],
        "study_execution": False,
        "study_scenes_loaded": 0,
        "oracle_access": False,
        "holdout_access": False,
        "semantic_calls_after_preflight": 0,
        "model_requested": contract["model_snapshot"],
        "reasoning_effort": contract["reasoning_effort"],
        "max_output_tokens": contract["max_output_tokens"],
        "truncation": contract["truncation"],
        "automatic_prompt_chunking": contract["automatic_prompt_chunking"],
        "worst_case_nodes": config["preflight_input"]["synthetic_nodes"],
        "worst_case_pairs": config["preflight_input"]["synthetic_pairs"],
        "prompt_variant": config["preflight_input"]["prompt_variant"],
        "prompt_render_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest().upper(),
        "dependencies": dependencies,
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "openai_sdk_version": openai.__version__,
    }
    if not execute:
        return {**base, "status": "PASS_DRY_RUN", "provider_calls": 0, "rendered_prompt_chars": len(prompt)}
    if output_path.is_file():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if existing.get("status") == "PASS":
            return {"status": "PASS_CACHED_PREFLIGHT", "provider_calls": 0, "artifact": str(output_path.relative_to(ROOT))}
        raise RuntimeError("preflight artifact already exists with non-PASS status; separate retry authorization required")
    started = time.perf_counter()
    try:
        client = OpenAI(api_key=load_key(), max_retries=0)
        response = client.responses.create(
            model=contract["model_snapshot"], input=prompt,
            reasoning={"effort": contract["reasoning_effort"]},
            max_output_tokens=contract["max_output_tokens"],
            service_tier=contract["service_tier"], store=contract["store"],
            text={"format": {"type": "json_schema", "name": "semantic_sentence_id_response_v1", "schema": json.loads((ROOT / contract["schema"]).read_text(encoding="utf-8")), "strict": True}},
            metadata={"task": config["task"], "study_execution": "false"},
        )
        raw_text = response.output_text or ""
        validate_response(raw_text, int(config["preflight_input"]["synthetic_pairs"]))
        usage = response.usage
        record = {**base, "status": "PASS", "provider_calls": 1, "model": response.model,
                  "request_id": getattr(response, "_request_id", None), "response_status": response.status,
                  "input_tokens": int(usage.input_tokens), "output_tokens": int(usage.output_tokens),
                  "reasoning_tokens": int(getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0),
                  "total_tokens": int(getattr(usage, "total_tokens", usage.input_tokens + usage.output_tokens)),
                  "response_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest().upper(),
                  "latency_ms": round((time.perf_counter() - started) * 1000),
                  "context_limit_check": "provider_completed_without_truncation"}
    except Exception as exc:
        record = {**base, "status": "FAIL", "provider_calls": 1, "error_type": type(exc).__name__,
                  "error_message": str(exc)[:1000], "latency_ms": round((time.perf_counter() - started) * 1000)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical(record))
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = run(args.config, execute=args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"PASS", "PASS_CACHED_PREFLIGHT", "PASS_DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
