"""Run/replay the frozen T12 v3 five-condition development matrix."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_t12_v3_oracle_development as oracle_runner  # noqa: E402
from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.causalds_scoring import load_official_target  # noqa: E402
from fourgraph.graph_contract import (  # noqa: E402
    GraphArtifact,
    canonical_json_bytes,
    sha256_hex,
)
from fourgraph.llm_backend import LLMCallRequest  # noqa: E402
from fourgraph.reasoner import (  # noqa: E402
    TASKS,
    conservative_target,
    load_reasoner_query,
    noncausal_glossary,
    score_answer,
)
from fourgraph.reasoner_v2 import (  # noqa: E402
    CanonicalResponseCache,
    build_cache_identity,
    parse_task_specific_response,
    v2_query_view,
)
from fourgraph.t12_openai_backend import T12OpenAIResponsesBackend  # noqa: E402


DEFAULT_CONFIG = Path("configs/t12_v3_openai_mini_full_development.yaml")


def _graph_manifest(path: Path) -> dict[str, GraphArtifact]:
    result: dict[str, GraphArtifact] = {}
    for number, row in enumerate(oracle_runner._rows(path), 1):
        artifact = GraphArtifact.from_dict(row)
        if artifact.scene_id in result:
            raise ValueError(f"Duplicate graph scene at {path}:{number}")
        result[artifact.scene_id] = artifact
    return result


def _validate_candidate(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    if config.get("schema_version") != "fourgraph.t12_v3_full_development_candidate.v1":
        raise RuntimeError("Unsupported full-development candidate schema")
    live = config.get("live_execution", {})
    if live != {
        "allowed": True,
        "next_action": "full_development_matrix_175",
        "t13_auto_start_allowed": False,
        "holdout_auto_start_allowed": False,
    }:
        raise RuntimeError("Candidate is not authorized for only the full development matrix")
    if config["holdout"]["accessed"] is not False:
        raise RuntimeError("Full-development candidate opened holdout")

    parent = config["parent_oracle_development"]
    for path_key, hash_key in (
        ("config", "config_sha256"),
        ("audit", "audit_sha256"),
        ("scores", "scores_sha256"),
        ("raw_log", "raw_log_sha256"),
        ("cache", "cache_sha256"),
    ):
        path = PROJECT_ROOT / parent[path_key]
        if not path.is_file() or sha256_hex(path.read_bytes()) != parent[hash_key]:
            raise RuntimeError(f"Frozen Oracle-development parent changed: {path_key}")
    parent_config = oracle_runner._object(PROJECT_ROOT / parent["config"], yaml_file=True)
    parent_audit = oracle_runner._object(PROJECT_ROOT / parent["audit"])
    if not parent_audit.get("oracle_development_passed") or not parent_audit.get(
        "full_development_matrix_eligible"
    ):
        raise RuntimeError("Oracle-development parent did not authorize the matrix")
    for field in ("reasoner", "graph_encoding", "evidence_contract"):
        if config[field] != parent_config[field]:
            raise RuntimeError(f"Full development changed frozen field: {field}")
    if config["frozen_reasoner_inputs"] != parent_config["frozen_reasoner_inputs"]:
        raise RuntimeError("Full development changed frozen prompt/schema inputs")
    benchmark_fields = (
        "split_manifest",
        "split_manifest_sha256",
        "task_manifest",
        "task_manifest_sha256",
        "oracle_loader_config",
        "oracle_loader_config_sha256",
        "variant",
        "cohort",
        "split",
        "scene_ids",
        "scenes",
        "tasks_per_scene",
    )
    if any(
        config["frozen_benchmark_inputs"][field]
        != parent_config["frozen_benchmark_inputs"][field]
        for field in benchmark_fields
    ):
        raise RuntimeError("Full development changed frozen benchmark inputs")
    if config_path != (PROJECT_ROOT / DEFAULT_CONFIG).resolve() and not config_path.is_file():
        raise RuntimeError("Full-development candidate path is invalid")
    return parent_audit


def _load_graphs(
    config: dict[str, Any], source_root: Path, graph_dev_ids: tuple[str, ...]
) -> list[tuple[str, dict[str, GraphArtifact]]]:
    result: list[tuple[str, dict[str, GraphArtifact]]] = []
    conditions = config["graph_conditions"]
    expected_names = [
        "G_LLM",
        "G_SCD_RAW",
        "G_SCD_PROJECTED",
        "G_HYBRID",
        "G_ORACLE",
    ]
    if [item["condition"] for item in conditions] != expected_names:
        raise RuntimeError("Frozen five-condition order changed")
    for item in conditions:
        if "manifest" in item:
            manifest_path = PROJECT_ROOT / item["manifest"]
            audit_path = PROJECT_ROOT / item["audit"]
            if sha256_hex(manifest_path.read_bytes()) != item["manifest_sha256"]:
                raise RuntimeError(f"Frozen graph manifest changed: {item['condition']}")
            if sha256_hex(audit_path.read_bytes()) != item["audit_sha256"]:
                raise RuntimeError(f"Frozen graph audit changed: {item['condition']}")
            audit = oracle_runner._object(audit_path)
            audit_holdout = audit.get(
                "holdout_accessed", (audit.get("scope") or {}).get("holdout_accessed")
            )
            if audit_holdout is not False:
                raise RuntimeError(f"Graph audit accessed holdout: {item['condition']}")
            graphs = _graph_manifest(manifest_path)
        else:
            oracle_sha = config["frozen_benchmark_inputs"][
                "oracle_loader_config_sha256"
            ]
            graphs = {
                scene_id: load_causalds_oracle_graph(
                    source_root, scene_id, config_sha256=oracle_sha
                ).graph_artifact
                for scene_id in graph_dev_ids
            }
        if set(graphs) != set(graph_dev_ids):
            raise RuntimeError(f"Graph condition does not cover graph-dev=8: {item['condition']}")
        if any(graph.graph_type != item["graph_type"] for graph in graphs.values()):
            raise RuntimeError(f"Graph type changed: {item['condition']}")
        result.append((item["condition"], graphs))
    return result


def _chosen_raw(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (item for item in reversed(history) if item["validation_error"] is None),
        None,
    )


def _service_calls(
    keys: set[str],
    parent_history: dict[str, list[dict[str, Any]]],
    new_history: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key in sorted(keys):
        histories = [value for value in (parent_history.get(key), new_history.get(key)) if value]
        if len(histories) != 1:
            raise RuntimeError(f"Canonical identity must have exactly one raw history: {key}")
        result.extend(histories[0])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--call-limit", type=int)
    args = parser.parse_args()
    if args.check and args.preflight:
        raise ValueError("Choose one of --check and --preflight")

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = oracle_runner._object(config_path, yaml_file=True)
    parent_audit = _validate_candidate(config_path, config)
    dev_ids, holdout_ids = oracle_runner._validate_benchmark(config)
    source_root = args.source_root.resolve()
    if any(scene in holdout_ids for scene in dev_ids):
        raise RuntimeError("Development matrix overlaps holdout")

    split = oracle_runner._object(
        PROJECT_ROOT / config["frozen_benchmark_inputs"]["split_manifest"]
    )
    graph_dev_ids = tuple(split["cohorts"]["graph"]["dev_ids"])
    graph_sets = _load_graphs(config, source_root, graph_dev_ids)
    bundle, prompt_bundle_sha256 = oracle_runner._load_prompt_bundle(config)

    reasoner = config["reasoner"]
    schema_paths: dict[str, Path] = {}
    provider_schemas: dict[str, dict[str, Any]] = {}
    for task_id, item in config["frozen_reasoner_inputs"]["response_schemas"].items():
        path = PROJECT_ROOT / item["path"]
        if sha256_hex(path.read_bytes()) != item["sha256"]:
            raise RuntimeError(f"Frozen response schema changed: {task_id}")
        schema_paths[task_id] = path
        provider_schemas[task_id] = oracle_runner._provider_schema(
            oracle_runner._object(path)
        )

    cases: list[dict[str, Any]] = []
    oracle_inputs: list[dict[str, Any]] = []
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError("Full development attempted holdout access")
        for task_id in TASKS:
            query, variable_map, public_tasks_sha = load_reasoner_query(
                source_root, scene_id, task_id
            )
            official = load_official_target(source_root, query, variable_map)
            glossary = noncausal_glossary(variable_map)
            for condition, graphs in graph_sets:
                graph = graphs[scene_id]
                if graph.scene_id != scene_id or graph.nodes != variable_map.node_ids:
                    raise RuntimeError(f"Graph/query universe mismatch: {scene_id}:{condition}")
                graph_view = graph.reasoner_view()
                query_view = v2_query_view(query)
                prompt = bundle.render(
                    task_id=task_id,
                    graph_reasoner_view=graph_view,
                    query_view=query_view,
                    glossary=glossary,
                )
                if any(variable.public_name in prompt for variable in variable_map.variables):
                    raise RuntimeError(f"Public semantic name leaked: {scene_id}:{condition}")
                decoding = oracle_runner._decoding_config(
                    reasoner, schema_paths[task_id], provider_schemas[task_id]
                )
                identity = build_cache_identity(
                    model_version=reasoner["model_version"],
                    prompt_template=bundle.template_for(task_id),
                    graph_reasoner_view=graph_view,
                    query=query,
                    glossary=glossary,
                    decoding_config=decoding,
                )
                uncertainty = conservative_target(graph.partial_graph, query)
                cases.append(
                    {
                        "case_id": f"{scene_id}:{task_id}:{condition}",
                        "scene_id": scene_id,
                        "task_id": task_id,
                        "condition": condition,
                        "query": query,
                        "variable_map": variable_map,
                        "graph": graph,
                        "graph_view": graph_view,
                        "glossary": glossary,
                        "prompt": prompt,
                        "official": official,
                        "uncertainty": uncertainty,
                        "identity": identity,
                        "public_tasks_sha256": public_tasks_sha,
                    }
                )
                if condition == "G_ORACLE":
                    oracle_inputs.append(
                        {
                            "scene_id": scene_id,
                            "task_id": task_id,
                            "graph_sha256": graph.graph_sha256,
                            "graph_artifact_sha256": graph.artifact_sha256,
                            "variable_mapping_sha256": variable_map.mapping_sha256,
                            "official_ground_truth_sha256": official.ground_truth_sha256,
                            "cache_key": identity.cache_key,
                        }
                    )

    expected = config["preflight_expectations"]
    if len(cases) != expected["records"] or len(oracle_inputs) != expected[
        "inherited_oracle_records"
    ]:
        raise RuntimeError("Full-development case count changed")
    panel_counts = Counter((case["condition"], case["task_id"]) for case in cases)
    if any(value != len(dev_ids) for value in panel_counts.values()) or len(
        panel_counts
    ) != len(graph_sets) * len(TASKS):
        raise RuntimeError("Full-development task panels are incomplete")

    parent = config["parent_oracle_development"]
    parent_scores = {
        (row["scene_id"], row["task_id"]): row
        for row in oracle_runner._rows(PROJECT_ROOT / parent["scores"])
    }
    if len(parent_scores) != 35:
        raise RuntimeError("Oracle-development parent scores changed")
    for item in oracle_inputs:
        parent_row = parent_scores[(item["scene_id"], item["task_id"])]
        if item["cache_key"] != parent_row["cache_key"]:
            raise RuntimeError("Oracle canonical identity changed from parent gate")

    outputs = config["outputs"]
    parent_cache_path = PROJECT_ROOT / parent["cache"]
    parent_raw_path = PROJECT_ROOT / parent["raw_log"]
    new_cache_path = PROJECT_ROOT / outputs["cache"]
    new_raw_path = PROJECT_ROOT / outputs["raw_log"]
    records_path = PROJECT_ROOT / outputs["records"]
    audit_path = PROJECT_ROOT / outputs["audit"]
    if (new_cache_path.exists() or new_raw_path.exists()) and not (
        args.resume or args.check or args.preflight
    ):
        raise FileExistsError("Existing full-development run found; use --resume or --check")

    parent_cache = CanonicalResponseCache.load(parent_cache_path)
    new_cache = CanonicalResponseCache.load(new_cache_path)
    parent_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    new_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in oracle_runner._rows(parent_raw_path):
        parent_history[row["cache_key"]].append(row)
    if new_raw_path.exists():
        for row in oracle_runner._rows(new_raw_path):
            new_history[row["cache_key"]].append(row)
    for histories in (parent_history, new_history):
        for history in histories.values():
            history.sort(key=lambda item: item["attempt"])
    if set(parent_history) & set(new_history):
        raise RuntimeError("Incremental raw log duplicated an inherited canonical identity")

    identity_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        identity_cases[case["identity"].cache_key].append(case)
    inherited_keys = {
        key
        for key, values in identity_cases.items()
        if parent_cache.get(values[0]["identity"]) is not None
    }
    new_cached_keys = {
        key
        for key, values in identity_cases.items()
        if new_cache.get(values[0]["identity"]) is not None
    }
    if inherited_keys & new_cached_keys:
        raise RuntimeError("Canonical identity exists in both parent and incremental cache")
    missing_keys = set(identity_cases) - inherited_keys - new_cached_keys

    if args.preflight:
        equivalent_groups = [
            {
                "cache_key": key,
                "records": len(values),
                "conditions": sorted({case["condition"] for case in values}),
            }
            for key, values in sorted(identity_cases.items())
            if len(values) > 1
        ]
        print(
            json.dumps(
                {
                    "preflight_passed": True,
                    "candidate_id": config["candidate_id"],
                    "scenes": len(dev_ids),
                    "tasks_per_scene": len(TASKS),
                    "graph_conditions": len(graph_sets),
                    "records": len(cases),
                    "unique_canonical_inputs": len(identity_cases),
                    "inherited_parent_identity_count": len(inherited_keys),
                    "inherited_record_count": sum(
                        len(identity_cases[key]) for key in inherited_keys
                    ),
                    "incremental_cached_identity_count": len(new_cached_keys),
                    "planned_new_api_calls_before_retries": len(missing_keys),
                    "identical_input_groups": equivalent_groups,
                    "holdout_accessed": False,
                    "api_calls": 0,
                },
                indent=2,
            )
        )
        return 0

    if args.check and (not new_raw_path.exists() or not new_cache_path.exists()):
        raise FileNotFoundError("--check requires the incremental raw log and cache")
    if not args.check:
        load_dotenv((PROJECT_ROOT / args.dotenv).resolve(), override=True)
        api_key = os.environ.get(reasoner["credential_env"], "")
        if not api_key:
            raise RuntimeError(f"Missing credential: {reasoner['credential_env']}")
    else:
        api_key = ""

    backends: dict[str, T12OpenAIResponsesBackend] = {}
    if not args.check:
        for task_id in TASKS:
            backend = T12OpenAIResponsesBackend(
                api_key=api_key,
                response_schema=provider_schemas[task_id],
                response_schema_name=oracle_runner.SCHEMA_NAMES[task_id],
                model_version=reasoner["model_version"],
                reasoning_effort=reasoner["reasoning_effort"],
                service_tier=reasoner["service_tier"],
                store=reasoner["store"],
                transport_max_retries=reasoner["transport_max_retries"],
                timeout_seconds=reasoner["timeout_seconds"],
                experiment_id="T12_v3_full_development",
            )
            if backend.sdk_version != reasoner["sdk_version"]:
                raise RuntimeError("OpenAI SDK version drift")
            backends[task_id] = backend

    records: list[dict[str, Any]] = []
    live_calls = 0
    for index, case in enumerate(cases, 1):
        identity = case["identity"]
        key = identity.cache_key
        query = case["query"]
        parent_text = parent_cache.get(identity)
        new_text = new_cache.get(identity)
        if parent_text is not None and new_text is not None:
            raise RuntimeError(f"Duplicate cached canonical identity: {key}")
        raw_text = parent_text if parent_text is not None else new_text
        if parent_text is not None:
            history = parent_history[key]
            response_origin = "inherited_oracle_development"
        else:
            history = new_history[key]
            response_origin = "full_development_cache" if new_text is not None else "full_development_live"
        chosen = _chosen_raw(history)
        parsed = None
        if raw_text is not None:
            if chosen is None or chosen["raw_text"] != raw_text:
                raise RuntimeError(f"Cached response lacks matching raw audit: {case['case_id']}")
            parsed = parse_task_specific_response(raw_text, query)
        elif args.check:
            raise RuntimeError(f"Missing cached full-development response: {case['case_id']}")
        else:
            validation_error: str | None = history[-1]["validation_error"] if history else None
            start_attempt = len(history)
            for attempt in range(start_attempt, reasoner["max_validation_retries"] + 1):
                incremental_calls = [item for values in new_history.values() for item in values]
                captured_cost = oracle_runner._cost(
                    incremental_calls,
                    config["budget"]["pricing_usd_per_million_tokens"],
                )["estimated_standard_cost_usd"]
                if captured_cost >= config["budget"]["incremental_captured_cost_stop_usd"]:
                    print(
                        json.dumps(
                            {
                                "partial": True,
                                "reason": "incremental_captured_cost_stop",
                                "estimated_incremental_cost_usd": captured_cost,
                                "live_calls": live_calls,
                                "holdout_accessed": False,
                            }
                        )
                    )
                    return 3
                call_prompt = case["prompt"]
                if validation_error is not None:
                    call_prompt += (
                        "\n\nYour previous output violated the response contract: "
                        f"{validation_error}. Return only the required one-field JSON object."
                    )
                request = LLMCallRequest(
                    scene_id=case["case_id"],
                    attempt=attempt,
                    prompt=call_prompt,
                    provider=reasoner["provider"],
                    model_id=reasoner["model_id"],
                    model_version=reasoner["model_version"],
                    temperature=0,
                    max_tokens=reasoner["max_output_tokens"],
                    seed=None,
                )
                response = backends[case["task_id"]].complete(request)
                live_calls += 1
                try:
                    parsed = parse_task_specific_response(response.raw_text, query)
                    validation_error = None
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    validation_error = str(exc)
                raw_record = {
                    "schema_version": "fourgraph.t12_v3_full_development_raw_call.v1",
                    "cache_key": key,
                    "case_id": case["case_id"],
                    "scene_id": case["scene_id"],
                    "task_id": case["task_id"],
                    "initiating_graph_condition": case["condition"],
                    "attempt": attempt,
                    "prompt": call_prompt,
                    "prompt_sha256": request.prompt_sha256,
                    "raw_text": response.raw_text,
                    "raw_sha256": response.raw_sha256,
                    "provider": response.provider,
                    "model_id": response.model_id,
                    "model_version": response.model_version,
                    "request_id": response.request_id,
                    "system_fingerprint": response.system_fingerprint,
                    "input_tokens": response.input_tokens,
                    "cached_input_tokens": response.cached_input_tokens,
                    "output_tokens": response.output_tokens,
                    "reasoning_tokens": response.reasoning_tokens,
                    "latency_ms": response.latency_ms,
                    "endpoint": response.endpoint,
                    "sdk_version": response.sdk_version,
                    "service_tier": response.service_tier,
                    "response_status": response.response_status,
                    "incomplete_reason": response.incomplete_reason,
                    "provider_response_json": response.provider_response_json,
                    "validation_error": validation_error,
                }
                oracle_runner._append_raw(new_raw_path, raw_record)
                history.append(raw_record)
                if parsed is not None:
                    raw_text = response.raw_text
                    chosen = raw_record
                    new_cache.put(identity, raw_text)
                    new_cache.write(new_cache_path)
                    break
            if parsed is None or raw_text is None or chosen is None:
                raise RuntimeError(f"Full-development response failed validation: {case['case_id']}")

        scores = score_answer(parsed, case["official"], case["uncertainty"])
        first_valid = bool(history and history[0]["validation_error"] is None)
        equivalent_cases = identity_cases[key]
        record = {
            "scene_id": case["scene_id"],
            "task_id": case["task_id"],
            "graph_condition": case["condition"],
            "graph_type": case["graph"].graph_type,
            "graph_view": case["graph"].graph_view,
            "graph_sha256": case["graph"].graph_sha256,
            "graph_artifact_sha256": case["graph"].artifact_sha256,
            "variable_mapping_sha256": case["variable_map"].mapping_sha256,
            "query_sha256": case["query"].sha256,
            "public_tasks_sha256": case["public_tasks_sha256"],
            "prompt_bundle_sha256": prompt_bundle_sha256,
            "prompt_sha256": sha256_hex(case["prompt"].encode("utf-8")),
            "cache_key": key,
            "canonical_equivalent_record_count": len(equivalent_cases),
            "canonical_equivalent_conditions": sorted(
                {item["condition"] for item in equivalent_cases}
            ),
            "response_origin": response_origin,
            "raw_response_sha256": sha256_hex(raw_text.encode("utf-8")),
            "parsed_response": parsed.to_dict(),
            "official_target": list(case["official"].accepted),
            "official_ground_truth_sha256": case["official"].ground_truth_sha256,
            "uncertainty_target": case["uncertainty"].to_dict(),
            **scores,
            "schema_version": "fourgraph.t12_v3_full_development_score.v1",
            "first_attempt_schema_compliant": first_valid,
            "attempts": len(history),
            "request_id": chosen["request_id"],
            "provider": chosen["provider"],
            "model_version": chosen["model_version"],
            "input_tokens": chosen["input_tokens"],
            "cached_input_tokens": chosen["cached_input_tokens"],
            "output_tokens": chosen["output_tokens"],
            "reasoning_tokens": chosen["reasoning_tokens"],
            "latency_ms": chosen["latency_ms"],
        }
        records.append(record)
        print(
            json.dumps(
                {
                    "record": index,
                    "case_id": case["case_id"],
                    "mode": response_origin,
                    "oracle_answer_accuracy": scores["oracle_answer_accuracy"],
                    "uncertainty_aware_correctness": scores[
                        "uncertainty_aware_correctness"
                    ],
                }
            ),
            flush=True,
        )
        if args.call_limit is not None and live_calls >= args.call_limit:
            print(json.dumps({"partial": True, "live_calls": live_calls}))
            return 0

    record_payload = b"".join(
        canonical_json_bytes(record, newline=True) for record in records
    )
    selected_keys = set(identity_cases)
    all_services = _service_calls(selected_keys, parent_history, new_history)
    inherited_services = _service_calls(inherited_keys, parent_history, new_history)
    new_services = _service_calls(selected_keys - inherited_keys, parent_history, new_history)
    pricing = config["budget"]["pricing_usd_per_million_tokens"]

    condition_summary: dict[str, dict[str, Any]] = {}
    for condition, _ in graph_sets:
        subset = [record for record in records if record["graph_condition"] == condition]
        condition_summary[condition] = {
            "records": len(subset),
            "oracle_answer_correct": sum(row["oracle_answer_accuracy"] for row in subset),
            "oracle_answer_accuracy": oracle_runner._rate(
                sum(row["oracle_answer_accuracy"] for row in subset), len(subset)
            ),
            "uncertainty_aware_correct": sum(
                row["uncertainty_aware_correctness"] for row in subset
            ),
            "uncertainty_aware_correctness": oracle_runner._rate(
                sum(row["uncertainty_aware_correctness"] for row in subset), len(subset)
            ),
            "undetermined_targets": sum(
                row["uncertainty_target"]["status"] == "undetermined" for row in subset
            ),
            "undetermined_responses": sum(
                row["parsed_response"]["status"] == "undetermined" for row in subset
            ),
        }

    task_condition_summary: dict[str, dict[str, Any]] = {}
    for condition, _ in graph_sets:
        task_condition_summary[condition] = {}
        for task_id in TASKS:
            subset = [
                row
                for row in records
                if row["graph_condition"] == condition and row["task_id"] == task_id
            ]
            task_condition_summary[condition][task_id] = {
                "correct": sum(row["oracle_answer_accuracy"] for row in subset),
                "accuracy": oracle_runner._rate(
                    sum(row["oracle_answer_accuracy"] for row in subset), len(subset)
                ),
            }

    oracle_matches = 0
    for row in records:
        if row["graph_condition"] != "G_ORACLE":
            continue
        parent_row = parent_scores[(row["scene_id"], row["task_id"])]
        if (
            row["cache_key"] == parent_row["cache_key"]
            and row["raw_response_sha256"] == parent_row["raw_response_sha256"]
            and canonical_json_bytes(row["parsed_response"])
            == canonical_json_bytes(parent_row["parsed_response"])
            and row["oracle_answer_accuracy"] == parent_row["oracle_answer_accuracy"]
        ):
            oracle_matches += 1

    first_attempt = sum(row["first_attempt_schema_compliant"] for row in records)
    gates = config["full_development_gate"]
    gate_results = {
        "final_parse_success": len(records) == gates["final_parse_success_count"],
        "first_attempt_schema_compliance": first_attempt
        >= gates["first_attempt_schema_compliance_min_count"],
        "inherited_oracle_response_match": oracle_matches
        == gates["inherited_oracle_response_match_count"],
        "canonical_identical_inputs_share_one_response": all(
            len({row["raw_response_sha256"] for row in records if row["cache_key"] == key})
            == 1
            for key in identity_cases
        ),
        "all_conditions_have_complete_task_panel": all(
            value == len(dev_ids) for value in panel_counts.values()
        ),
        "model_snapshot_match": all(
            row["model_version"] == reasoner["model_version"] for row in records
        ),
        "usage_present": all(
            row["input_tokens"] is not None
            and row["output_tokens"] is not None
            and row["reasoning_tokens"] is not None
            for row in records
        ),
        "holdout_not_accessed": True,
    }
    passed = all(gate_results.values())
    output_values = [int(item["output_tokens"]) for item in all_services]
    reasoning_values = [int(item["reasoning_tokens"]) for item in all_services]
    latency_values = [int(item["latency_ms"]) for item in all_services]
    audit = {
        "schema_version": "fourgraph.t12_v3_full_development_audit.v1",
        "candidate_id": config["candidate_id"],
        "config_sha256": sha256_hex(config_path.read_bytes()),
        "runner_sha256": sha256_hex(Path(__file__).read_bytes()),
        "oracle_runner_dependency_sha256": parent_audit["runner_sha256"],
        "parent_oracle_development_audit_sha256": parent["audit_sha256"],
        "provider": reasoner["provider"],
        "model_id": reasoner["model_id"],
        "model_version": reasoner["model_version"],
        "reasoning_effort": reasoner["reasoning_effort"],
        "max_output_tokens": reasoner["max_output_tokens"],
        "development_scenes": len(dev_ids),
        "tasks_per_scene": len(TASKS),
        "graph_conditions": [condition for condition, _ in graph_sets],
        "records": len(records),
        "unique_canonical_inputs": len(identity_cases),
        "canonical_reused_records": len(records) - len(identity_cases),
        "canonical_equivalence_groups": sum(
            len(values) > 1 for values in identity_cases.values()
        ),
        "inherited_parent_identity_count": len(inherited_keys),
        "inherited_parent_record_count": sum(
            len(identity_cases[key]) for key in inherited_keys
        ),
        "new_identity_count": len(selected_keys - inherited_keys),
        "inherited_oracle_response_matches": oracle_matches,
        "first_attempt_schema_compliance": first_attempt,
        "captured_unique_calls": len(all_services),
        "captured_inherited_calls": len(inherited_services),
        "captured_incremental_calls": len(new_services),
        "incremental_retry_calls": len(new_services) - len(selected_keys - inherited_keys),
        "completed_calls": sum(item["response_status"] == "completed" for item in all_services),
        "incomplete_calls": sum(item["response_status"] == "incomplete" for item in all_services),
        "condition_summary": condition_summary,
        "task_condition_summary": task_condition_summary,
        "overall_oracle_answer_accuracy": oracle_runner._rate(
            sum(row["oracle_answer_accuracy"] for row in records), len(records)
        ),
        "overall_uncertainty_aware_correctness": oracle_runner._rate(
            sum(row["uncertainty_aware_correctness"] for row in records), len(records)
        ),
        "max_output_token_utilization": round(
            max(output_values) / reasoner["max_output_tokens"], 8
        ),
        "reasoning_tokens_distribution": {
            "min": min(reasoning_values),
            "median": oracle_runner._median(reasoning_values),
            "max": max(reasoning_values),
        },
        "latency_ms_distribution": {
            "min": min(latency_values),
            "median": oracle_runner._median(latency_values),
            "max": max(latency_values),
        },
        "usage_total_including_inherited": oracle_runner._cost(all_services, pricing),
        "usage_inherited_oracle_development": oracle_runner._cost(
            inherited_services, pricing
        ),
        "usage_incremental_full_development": oracle_runner._cost(new_services, pricing),
        "gate_thresholds": gates,
        "gate_results": gate_results,
        "full_development_matrix_passed": passed,
        "reasoner_frozen_for_holdout": passed,
        "holdout_reasoner_ready": passed,
        "t13_eligible": passed,
        "holdout_accessed": False,
        "records_sha256": sha256_hex(record_payload),
        "parent_raw_log_sha256": sha256_hex(parent_raw_path.read_bytes()),
        "parent_cache_sha256": sha256_hex(parent_cache_path.read_bytes()),
        "incremental_raw_log_sha256": sha256_hex(new_raw_path.read_bytes()),
        "incremental_cache_sha256": sha256_hex(new_cache_path.read_bytes()),
    }
    audit_payload = canonical_json_bytes(audit, newline=True)
    if args.check:
        if records_path.read_bytes() != record_payload:
            raise RuntimeError("Full-development scores do not reproduce byte-for-byte")
        if audit_path.read_bytes() != audit_payload:
            raise RuntimeError("Full-development audit does not reproduce byte-for-byte")
    else:
        records_path.parent.mkdir(parents=True, exist_ok=True)
        records_path.write_bytes(record_payload)
        audit_path.write_bytes(audit_payload)
    print(json.dumps({**audit, "live_calls_this_run": live_calls}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
