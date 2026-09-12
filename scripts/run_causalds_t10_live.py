"""Capture or resume the frozen T10 Hybrid H1 development calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.causalds_public import load_llm_graph_input  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.hybrid_graph import (  # noqa: E402
    HybridPolicy,
    build_hybrid_graph,
    load_graph_jsonl,
    load_prompt_template,
)
from fourgraph.llm_backend import ReplayBackend  # noqa: E402
from fourgraph.t10_openai_backend import T10OpenAIResponsesBackend  # noqa: E402


DEFAULT_CONFIG = Path("configs/t10_hybrid_graph_builder.yaml")


def _mapping(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if yaml_file else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def _policy(config: dict[str, Any]) -> HybridPolicy:
    llm = config["llm"]
    return HybridPolicy(
        provider=llm["provider"],
        model_id=llm["model_id"],
        model_version=llm["model_version"],
        temperature=llm["temperature"],
        max_tokens=llm["max_tokens"],
        seed=llm["seed"],
        max_validation_retries=llm["max_validation_retries"],
    )


def _default_raw_log(config: dict[str, Any]) -> Path:
    model = str(config["llm"]["model_version"]).replace("/", "_")
    return PROJECT_ROOT / config["logging"]["raw_log_cache"] / f"{model}_dev.jsonl"


def _append_attempts(path: Path, result: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        for attempt in result.attempts:
            stream.write(canonical_json_bytes(attempt.raw_log_record(result.scene_id), newline=True))
        stream.flush()


def _validate_frozen_model(config: dict[str, Any]) -> None:
    llm = config["llm"]
    t08 = _mapping(PROJECT_ROOT / llm["source_freeze"], yaml_file=True)["llm"]
    keys = (
        "provider", "model_id", "model_version", "endpoint", "sdk", "sdk_version",
        "credential_env", "service_tier", "store", "structured_outputs",
        "reasoning_effort", "temperature", "max_tokens", "seed",
        "max_validation_retries", "transport_max_retries", "timeout_seconds",
    )
    drift = {key: (t08.get(key), llm.get(key)) for key in keys if t08.get(key) != llm.get(key)}
    if drift:
        raise RuntimeError(f"T10 semantic model/config drifted from T08: {drift}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--raw-log", type=Path)
    parser.add_argument("--scene-id")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = _mapping(config_path, yaml_file=True)
    _validate_frozen_model(config)
    llm = config["llm"]
    if llm["provider"] != "openai" or llm["endpoint"] != "/v1/responses" or llm["model_id"] != llm["model_version"]:
        raise ValueError("T10 requires the immutable T08 OpenAI Responses snapshot")

    split = _mapping(PROJECT_ROOT / config["scope"]["split_manifest"])
    cohort = split["cohorts"][config["scope"]["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if len(dev_ids) != config["scope"]["expected_scenes"] or set(dev_ids) & holdout_ids:
        raise ValueError("Frozen development scope changed")
    if args.scene_id is not None:
        if args.scene_id not in dev_ids:
            raise ValueError("--scene-id must name one frozen development scene")
        selected_ids = (args.scene_id,)
    else:
        selected_ids = dev_ids

    parents = load_graph_jsonl(PROJECT_ROOT / config["parent"]["raw_cpdag"])
    if set(parents) != set(dev_ids):
        raise RuntimeError("T09 parent manifest does not contain exactly eight dev scenes")

    raw_log = (args.raw_log or _default_raw_log(config)).resolve()
    if raw_log.exists() and not args.resume:
        raise FileExistsError(f"Raw log already exists; use --resume: {raw_log}")
    replay = ReplayBackend.load(raw_log) if raw_log.exists() else None
    if replay is not None and not replay.scene_ids.issubset(dev_ids):
        raise RuntimeError("Raw T10 log contains a non-development scene")

    load_dotenv((PROJECT_ROOT / args.dotenv).resolve(), override=True)
    api_key = os.environ.get(llm["credential_env"], "")
    if not api_key:
        raise RuntimeError(f"Missing credential environment variable: {llm['credential_env']}")
    response_schema = _mapping(PROJECT_ROOT / config["prompt"]["response_schema"])
    schema_path = PROJECT_ROOT / config["prompt"]["response_schema"]
    if sha256_hex(schema_path.read_bytes()) != config["prompt"]["response_schema_sha256"]:
        raise RuntimeError("Frozen T10 response schema changed")
    for relative_path, expected_hash in config["freeze_anchors"].items():
        if sha256_hex((PROJECT_ROOT / relative_path).read_bytes()) != expected_hash:
            raise RuntimeError(f"Frozen T10 dependency changed: {relative_path}")
    backend = T10OpenAIResponsesBackend(
        api_key=api_key,
        response_schema=response_schema,
        service_tier=llm["service_tier"],
        reasoning_effort=llm["reasoning_effort"],
        store=llm["store"],
        transport_max_retries=llm["transport_max_retries"],
        timeout_seconds=llm["timeout_seconds"],
    )
    if backend.sdk_version != llm["sdk_version"]:
        raise RuntimeError(f"OpenAI SDK drift: expected={llm['sdk_version']}, actual={backend.sdk_version}")
    template, template_sha256 = load_prompt_template(PROJECT_ROOT / config["prompt"]["template"])
    if template_sha256 != config["prompt"]["template_sha256"]:
        raise RuntimeError("Frozen T10 prompt template changed")

    policy = _policy(config)
    config_sha256 = sha256_hex(config_path.read_bytes())
    successes = live_calls = total_tokens = 0
    for scene_id in selected_ids:
        if scene_id in holdout_ids:
            raise RuntimeError(f"T10 attempted holdout access: {scene_id}")
        evidence = load_llm_graph_input(args.source_root.resolve(), scene_id, variant=config["source"]["variant"])
        use_replay = replay is not None and replay.has_scene(scene_id)
        result = build_hybrid_graph(
            evidence,
            parents[scene_id],
            backend=replay if use_replay else backend,
            policy=policy,
            prompt_template=template,
            config_sha256=config_sha256,
        )
        if not use_replay:
            _append_attempts(raw_log, result)
            live_calls += len(result.attempts)
        scene_tokens = sum((item.response.input_tokens or 0) + (item.response.output_tokens or 0) for item in result.attempts)
        total_tokens += scene_tokens
        print(json.dumps({
            "scene_id": scene_id,
            "mode": "replay" if use_replay else "live",
            "success": result.success,
            "unresolved_edges": result.unresolved_edge_count,
            "attempts": len(result.attempts),
            "tokens": scene_tokens,
            "final_error": result.final_error,
        }, ensure_ascii=False), flush=True)
        if not result.success:
            return 2
        successes += 1

    print(json.dumps({
        "selected_scenes": len(selected_ids),
        "scenes_succeeded": successes,
        "live_calls_this_run": live_calls,
        "tokens_observed": total_tokens,
        "raw_log": str(raw_log),
        "holdout_accessed": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
