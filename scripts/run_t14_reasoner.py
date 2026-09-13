"""Run/replay the frozen T14 five-condition primary holdout reasoner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_t12_v3_oracle_development as helper  # noqa: E402
from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.causalds_scoring import load_official_target  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.graph_metrics import load_graph_artifact_jsonl  # noqa: E402
from fourgraph.llm_backend import LLMCallRequest  # noqa: E402
from fourgraph.reasoner import TASKS, conservative_target, load_reasoner_query, noncausal_glossary, score_answer  # noqa: E402
from fourgraph.reasoner_v2 import CanonicalResponseCache, build_cache_identity, parse_task_specific_response, v2_query_view  # noqa: E402
from fourgraph.t12_openai_backend import T12OpenAIResponsesBackend  # noqa: E402


CONDITIONS = ["G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID", "G_ORACLE"]


def obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def append_raw(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(canonical_json_bytes(record, newline=True))
        stream.flush()


def chosen(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((item for item in reversed(history) if item["validation_error"] is None), None)


def seeded_keys(keys: set[str], seed: int) -> list[str]:
    return sorted(keys, key=lambda key: hashlib.sha256(f"{seed}|{key}".encode()).hexdigest())


def build_context(source_root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any], dict[str, Path], dict[str, dict[str, Any]]]:
    t13_path = ROOT / "data/manifests/t13_holdout_execution.json"
    t13_audit = obj(ROOT / "data/manifests/t13_holdout_execution_audit.json")
    t13 = obj(t13_path)
    if sha256_hex(t13_path.read_bytes()) != t13_audit["execution_manifest_sha256"] or not t13_audit["verdict"]["t14_authorized"]:
        raise RuntimeError("T13 authorization failed")
    out_root = ROOT / t13["execution"]["outputs"]["t14_root"]
    seal_path = out_root / "non_oracle_seal.json"
    metric_audit = obj(out_root / "graph_metrics_audit.json")
    if not metric_audit["complete"] or metric_audit["non_oracle_seal_sha256"] != sha256_hex(seal_path.read_bytes()):
        raise RuntimeError("Reasoner cannot start before graph metrics complete")
    seal = obj(seal_path)
    primary_ids = t13["cohorts"]["primary_downstream"]["holdout_scene_ids"]
    graph_sets = {name: load_graph_artifact_jsonl(ROOT / seal["condition_files"][name]["path"]) for name in CONDITIONS[:-1]}
    graph_failures = {(item["condition"], item["scene_id"]): item for item in rows(ROOT / seal["failure_manifest"]["path"])}

    candidate = helper._object(ROOT / "configs/t12_v3_openai_mini_full_development.yaml", yaml_file=True)
    reasoner = candidate["reasoner"]
    bundle, bundle_sha = helper._load_prompt_bundle(candidate)
    schema_paths: dict[str, Path] = {}
    provider_schemas: dict[str, dict[str, Any]] = {}
    for task, item in candidate["frozen_reasoner_inputs"]["response_schemas"].items():
        path = ROOT / item["path"]
        if sha256_hex(path.read_bytes()) != item["sha256"]:
            raise RuntimeError(f"Reasoner schema drift: {task}")
        schema_paths[task] = path
        provider_schemas[task] = helper._provider_schema(helper._object(path))

    oracle_sha = sha256_hex((ROOT / "configs/t07_oracle_loader.yaml").read_bytes())
    oracles = {scene: load_causalds_oracle_graph(source_root, scene, config_sha256=oracle_sha) for scene in primary_ids}
    task_manifest = {(row["scene_id"], row["task_id"]) for row in rows(ROOT / "data/manifests/t13_primary_holdout_tasks.jsonl")}
    if task_manifest != {(scene, task) for scene in primary_ids for task in TASKS}:
        raise RuntimeError("T13 primary task manifest drift")

    cases: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for scene in primary_ids:
        loaded = oracles[scene]
        for task in TASKS:
            query, variable_map, public_tasks_sha = load_reasoner_query(source_root, scene, task)
            official = load_official_target(source_root, query, variable_map)
            if variable_map.mapping_sha256 != loaded.variable_map.mapping_sha256:
                raise RuntimeError("Oracle/query variable map mismatch")
            for condition in CONDITIONS:
                base = {"scene_id": scene, "task_id": task, "condition": condition, "query": query, "variable_map": variable_map, "official": official, "public_tasks_sha256": public_tasks_sha}
                if (condition, scene) in graph_failures:
                    cases.append({**base, "terminal_graph_failure": True})
                    continue
                graph = loaded.graph_artifact if condition == "G_ORACLE" else graph_sets[condition][scene]
                view = graph.reasoner_view()
                glossary = noncausal_glossary(variable_map)
                prompt = bundle.render(task_id=task, graph_reasoner_view=view, query_view=v2_query_view(query), glossary=glossary)
                if any(variable.public_name in prompt for variable in variable_map.variables):
                    raise RuntimeError("Public semantic name leaked into reasoner")
                decoding = helper._decoding_config(reasoner, schema_paths[task], provider_schemas[task])
                identity = build_cache_identity(model_version=reasoner["model_version"], prompt_template=bundle.template_for(task), graph_reasoner_view=view, query=query, glossary=glossary, decoding_config=decoding)
                case = {**base, "terminal_graph_failure": False, "graph": graph, "prompt": prompt, "identity": identity, "uncertainty": conservative_target(graph.partial_graph, query), "prompt_bundle_sha256": bundle_sha}
                cases.append(case)
                groups[identity.cache_key].append(case)
    if len(cases) != 500:
        raise RuntimeError("T14 reasoner schedule must contain 500 records")
    return t13, candidate, cases, groups, reasoner, schema_paths, provider_schemas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--call-limit", type=int)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    args = parser.parse_args()
    t13, candidate, cases, groups, reasoner, schema_paths, provider_schemas = build_context(args.source_root.resolve())
    out_root = ROOT / t13["execution"]["outputs"]["t14_root"]
    cache_path = ROOT / t13["execution"]["outputs"]["t14_cache"]
    attempt_path = ROOT / t13["execution"]["outputs"]["t14_attempt_log"]
    output_path = ROOT / t13["execution"]["outputs"]["t14_primary_scores"]
    cache = CanonicalResponseCache.load(cache_path)
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in rows(attempt_path):
        if item.get("phase") == "REASONER":
            history[item["cache_key"]].append(item)
    for value in history.values():
        value.sort(key=lambda item: item["attempt"])
    failure_path = out_root / "reasoner_failures.jsonl"
    failures = {item["cache_key"]: item for item in rows(failure_path)}
    missing = {key for key, values in groups.items() if cache.get(values[0]["identity"]) is None and key not in failures}
    if args.preflight:
        print(json.dumps({"preflight": True, "scheduled_records": 500, "graph_failure_records": sum(case["terminal_graph_failure"] for case in cases), "unique_canonical_inputs": len(groups), "cached": len(groups) - len(missing) - len(failures), "terminal_reasoner_failures": len(failures), "planned_new_calls_before_retries": len(missing)}, indent=2))
        return 0
    if args.check and missing:
        raise RuntimeError(f"T14 reasoner cache incomplete: {len(missing)} identities")
    if not args.check:
        load_dotenv(ROOT / args.dotenv, override=True)
        api_key = os.environ.get(reasoner["credential_env"], "")
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY")
    else:
        api_key = ""
    backends = {}
    if not args.check:
        for task in TASKS:
            backends[task] = T12OpenAIResponsesBackend(api_key=api_key, response_schema=provider_schemas[task], response_schema_name=helper.SCHEMA_NAMES[task], model_version=reasoner["model_version"], reasoning_effort=reasoner["reasoning_effort"], service_tier=reasoner["service_tier"], store=reasoner["store"], transport_max_retries=reasoner["transport_max_retries"], timeout_seconds=reasoner["timeout_seconds"], experiment_id="T14_P0_holdout")
            if backends[task].sdk_version != reasoner["sdk_version"]:
                raise RuntimeError("OpenAI SDK drift")

    live_calls = 0
    for key in seeded_keys(set(groups), t13["execution"]["reasoner_order_seed"]):
        case = groups[key][0]
        identity = case["identity"]
        if cache.get(identity) is not None or key in failures:
            continue
        validation_error = history[key][-1]["validation_error"] if history[key] else None
        parsed = None
        for attempt in range(len(history[key]), reasoner["max_validation_retries"] + 1):
            prompt = case["prompt"]
            if validation_error:
                prompt += f"\n\nYour previous output violated the response contract: {validation_error}. Return only the required one-field JSON object."
            request = LLMCallRequest(scene_id=f"{case['scene_id']}:{case['task_id']}", attempt=attempt, prompt=prompt, provider=reasoner["provider"], model_id=reasoner["model_id"], model_version=reasoner["model_version"], temperature=0, max_tokens=reasoner["max_output_tokens"], seed=None)
            response = backends[case["task_id"]].complete(request)
            live_calls += 1
            try:
                parsed = parse_task_specific_response(response.raw_text, case["query"])
                validation_error = None
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                validation_error = str(exc)
            record = {"schema_version": "fourgraph.t14_reasoner_raw_call.v1", "phase": "REASONER", "cache_key": key, "scene_id": case["scene_id"], "task_id": case["task_id"], "initiating_graph_condition": case["condition"], "attempt": attempt, "prompt": prompt, "prompt_sha256": request.prompt_sha256, "raw_text": response.raw_text, "raw_sha256": response.raw_sha256, "provider": response.provider, "model_id": response.model_id, "model_version": response.model_version, "request_id": response.request_id, "system_fingerprint": response.system_fingerprint, "input_tokens": response.input_tokens, "cached_input_tokens": response.cached_input_tokens, "output_tokens": response.output_tokens, "reasoning_tokens": response.reasoning_tokens, "latency_ms": response.latency_ms, "endpoint": response.endpoint, "sdk_version": response.sdk_version, "service_tier": response.service_tier, "response_status": response.response_status, "incomplete_reason": response.incomplete_reason, "provider_response_json": response.provider_response_json, "validation_error": validation_error}
            append_raw(attempt_path, record)
            history[key].append(record)
            if parsed is not None:
                cache.put(identity, response.raw_text)
                cache.write(cache_path)
                break
        if parsed is None:
            failures[key] = {"schema_version": "fourgraph.t14_reasoner_failure.v1", "cache_key": key, "scene_id": case["scene_id"], "task_id": case["task_id"], "attempts": len(history[key]), "final_error": validation_error, "terminal": True}
            failure_path.write_bytes(b"".join(canonical_json_bytes(failures[item], newline=True) for item in sorted(failures)))
        print(json.dumps({"reasoner_identity": len(groups) - len(missing) + live_calls, "cache_key": key[:12], "live_calls": live_calls, "success": parsed is not None}), flush=True)
        if args.call_limit is not None and live_calls >= args.call_limit:
            print(json.dumps({"partial": True, "live_calls": live_calls}))
            return 0

    records = []
    for case in cases:
        if case["terminal_graph_failure"]:
            records.append({"schema_version": "fourgraph.t14_primary_score.v1", "scene_id": case["scene_id"], "task_id": case["task_id"], "graph_condition": case["condition"], "status": "graph_failure", "cache_key": None, "graph_sha256": None, "parsed_response": None, "official_target": list(case["official"].accepted), "uncertainty_target": None, "oracle_answer_accuracy": 0, "uncertainty_aware_correctness": 0, "attempts": 0, "request_id": None, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "latency_ms": 0})
            continue
        identity, query, key = case["identity"], case["query"], case["identity"].cache_key
        raw_text = cache.get(identity)
        selected = chosen(history[key])
        if raw_text is None or selected is None:
            records.append({"schema_version": "fourgraph.t14_primary_score.v1", "scene_id": case["scene_id"], "task_id": case["task_id"], "graph_condition": case["condition"], "status": "reasoner_failure", "cache_key": key, "graph_sha256": case["graph"].graph_sha256, "parsed_response": None, "official_target": list(case["official"].accepted), "uncertainty_target": case["uncertainty"].to_dict(), "oracle_answer_accuracy": 0, "uncertainty_aware_correctness": 0, "attempts": len(history[key]), "request_id": None, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "latency_ms": 0})
            continue
        parsed = parse_task_specific_response(raw_text, query)
        scores = score_answer(parsed, case["official"], case["uncertainty"])
        records.append({"schema_version": "fourgraph.t14_primary_score.v1", "scene_id": case["scene_id"], "task_id": case["task_id"], "graph_condition": case["condition"], "status": "answered", "cache_key": key, "graph_sha256": case["graph"].graph_sha256, "parsed_response": parsed.to_dict(), "official_target": list(case["official"].accepted), "uncertainty_target": case["uncertainty"].to_dict(), **scores, "attempts": len(history[key]), "request_id": selected["request_id"], "input_tokens": selected["input_tokens"], "cached_input_tokens": selected["cached_input_tokens"], "output_tokens": selected["output_tokens"], "reasoning_tokens": selected["reasoning_tokens"], "latency_ms": selected["latency_ms"]})
    if len(records) != 500:
        raise RuntimeError("T14 primary score count changed")
    payload = b"".join(canonical_json_bytes(item, newline=True) for item in records)
    if args.check:
        if output_path.read_bytes() != payload:
            raise RuntimeError("T14 score replay differs byte-for-byte")
    else:
        output_path.write_bytes(payload)
    services = [item for values in history.values() for item in values]
    audit = {"schema_version": "fourgraph.t14_reasoner_audit.v1", "logical_run_id": t13["execution"]["logical_run_id"], "scheduled_records": 500, "answered_records": sum(item["status"] == "answered" for item in records), "graph_failure_records": sum(item["status"] == "graph_failure" for item in records), "reasoner_failure_records": sum(item["status"] == "reasoner_failure" for item in records), "unique_canonical_inputs": len(groups), "canonical_reused_records": sum(not case["terminal_graph_failure"] for case in cases) - len(groups), "captured_calls": len(services), "validation_retries": len(services) - len(groups), "model_version": reasoner["model_version"], "records_sha256": sha256_hex(payload), "cache_sha256": sha256_hex(cache_path.read_bytes()), "attempt_log_sha256": sha256_hex(attempt_path.read_bytes()), "usage": helper._cost(services, {"uncached_input": 0.75, "cached_input": 0.075, "output_including_reasoning": 4.50}), "aggregate_accuracy_deferred_to_t15": True, "complete": True}
    audit_path = out_root / "reasoner_audit.json"
    audit_bytes = canonical_json_bytes(audit, newline=True)
    if args.check:
        if audit_path.read_bytes() != audit_bytes:
            raise RuntimeError("T14 reasoner audit replay differs")
    else:
        audit_path.write_bytes(audit_bytes)
    print(json.dumps({"records": 500, "answered": audit["answered_records"], "graph_failures": audit["graph_failure_records"], "reasoner_failures": audit["reasoner_failure_records"], "unique_inputs": len(groups), "calls": len(services), "cost_usd": audit["usage"]["estimated_standard_cost_usd"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
