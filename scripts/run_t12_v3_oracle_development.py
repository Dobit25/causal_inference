"""Run/replay the separately authorized T12 v3 G_ORACLE development gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.causalds_scoring import load_official_target  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.llm_backend import LLMCallRequest  # noqa: E402
from fourgraph.reasoner import (  # noqa: E402
    TASKS,
    OfficialTarget,
    ReasonerQuery,
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
from fourgraph.reasoner_v3 import PromptV3Bundle  # noqa: E402
from fourgraph.t12_openai_backend import T12OpenAIResponsesBackend  # noqa: E402


DEFAULT_CONFIG = Path("configs/t12_v3_openai_mini_oracle_dev.yaml")
SCHEMA_NAMES = {
    "identification__one_valid_adjustment_set": "t12_v3_one_valid_adjustment_set",
    "identification__all_minimal_adjustment_sets": "t12_v3_all_minimal_adjustment_sets",
    "identification__minimal_adjustment_set_size": "t12_v3_minimal_adjustment_set_size",
    "identification__n_valid_adjustment_sets": "t12_v3_n_valid_adjustment_sets",
    "bias_diagnostic__forbidden_controls_list": "t12_v3_forbidden_controls_list",
}


def _object(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    value = (
        yaml.safe_load(path.read_text(encoding="utf-8"))
        if yaml_file
        else json.loads(path.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Translate frozen local schemas to the equivalent OpenAI strict subset."""

    def translate(value: Any) -> Any:
        if isinstance(value, list):
            return [translate(item) for item in value]
        if not isinstance(value, dict):
            return value
        translated: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"$schema", "pattern", "uniqueItems", "minimum"}:
                continue
            translated["anyOf" if key == "oneOf" else key] = translate(item)
        return translated

    return translate(schema)


def _append_raw(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(canonical_json_bytes(record, newline=True))
        stream.flush()


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 8) if denominator else 0.0


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2:
        return float(values[middle])
    return (values[middle - 1] + values[middle]) / 2


def _cost(records: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, Any]:
    input_tokens = sum(int(item.get("input_tokens") or 0) for item in records)
    cached = sum(int(item.get("cached_input_tokens") or 0) for item in records)
    output = sum(int(item.get("output_tokens") or 0) for item in records)
    reasoning = sum(int(item.get("reasoning_tokens") or 0) for item in records)
    estimated = (
        (input_tokens - cached) * prices["uncached_input"]
        + cached * prices["cached_input"]
        + output * prices["output_including_reasoning"]
    ) / 1_000_000
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens_including_reasoning": output,
        "reasoning_tokens": reasoning,
        "estimated_standard_cost_usd": round(estimated, 8),
    }


def _answer_class(task_id: str, official: OfficialTarget) -> str:
    if "no_backdoor" in official.accepted:
        return "no_valid_adjustment_set"
    if task_id == TASKS[0]:
        is_empty = () in official.accepted
    elif task_id == TASKS[1]:
        is_empty = official.accepted == (((),),)
    elif task_id in {TASKS[2], TASKS[3]}:
        is_empty = official.accepted == (0,)
    else:
        is_empty = official.accepted == ((),)
    return "valid_empty_set" if is_empty else "valid_nonempty_set"


def _required_empty_representation(
    task_id: str, official: OfficialTarget
) -> str | None:
    if task_id == TASKS[1] and official.accepted == (((),),):
        return "list_containing_empty_list"
    if task_id == TASKS[2] and official.accepted == (0,):
        return "integer_zero"
    if task_id == TASKS[4] and official.accepted == ((),):
        return "empty_list"
    return None


def _targets_equivalent(
    task_id: str, official: OfficialTarget, graph_target: Any
) -> bool:
    if graph_target.status != "answered":
        return False
    if task_id == TASKS[0]:
        return set(graph_target.accepted) == set(official.accepted)
    return graph_target.accepted == official.accepted


def _load_prompt_bundle(config: dict[str, Any]) -> tuple[PromptV3Bundle, str]:
    frozen = config["frozen_reasoner_inputs"]
    contract_path = PROJECT_ROOT / frozen["prompt_contract"]
    if sha256_hex(contract_path.read_bytes()) != frozen["prompt_contract_sha256"]:
        raise RuntimeError("Frozen T12 v3 prompt contract hash changed")
    contract = _object(contract_path)
    components = contract["prompt_components"]
    bundle = PromptV3Bundle.load(
        base_path=PROJECT_ROOT / components["base"]["path"],
        module_paths={
            task: PROJECT_ROOT / item["path"]
            for task, item in components["modules"].items()
        },
    )
    if components["bundle_sha256"] != frozen["prompt_bundle_sha256"]:
        raise RuntimeError("Frozen T12 v3 prompt bundle hash changed")
    if sha256_hex(bundle.base_template.encode("utf-8")) != components["base"]["sha256"]:
        raise RuntimeError("Frozen T12 v3 base prompt changed")
    for task_id, module in bundle.modules.items():
        expected = components["modules"][task_id]
        if sha256_hex(module.encode("utf-8")) != expected["sha256"]:
            raise RuntimeError(f"Frozen T12 v3 prompt module changed: {task_id}")
        assembled = sha256_hex(bundle.template_for(task_id).encode("utf-8"))
        if assembled != expected["assembled_template_sha256"]:
            raise RuntimeError(f"Frozen T12 v3 assembled prompt changed: {task_id}")
    return bundle, components["bundle_sha256"]


def _validate_candidate(config_path: Path, config: dict[str, Any]) -> None:
    if config.get("schema_version") != "fourgraph.t12_v3_oracle_development_candidate.v1":
        raise RuntimeError("Unsupported Oracle-development candidate schema")
    live = config.get("live_execution", {})
    if live.get("allowed") is not True or live.get("next_action") != "oracle_development_35":
        raise RuntimeError("Candidate is not authorized for Oracle-development only")
    if live.get("full_development_matrix_auto_start_allowed") is not False:
        raise RuntimeError("Oracle-development candidate may not auto-start full matrix")
    if live.get("t13_auto_start_allowed") is not False:
        raise RuntimeError("Oracle-development candidate may not auto-start T13")
    if config.get("holdout") != {
        "accessed": False,
        "eligible": False,
        "reason": "oracle_development_gate_must_pass_then_full_development_reasoner_must_freeze",
    }:
        raise RuntimeError("Oracle-development holdout boundary changed")

    parent = config["parent_candidate"]
    parent_path = PROJECT_ROOT / parent["config"]
    if sha256_hex(parent_path.read_bytes()) != parent["config_sha256"]:
        raise RuntimeError("Parent conformance candidate hash changed")
    parent_config = _object(parent_path, yaml_file=True)
    audit_path = PROJECT_ROOT / parent["conformance_audit"]
    if sha256_hex(audit_path.read_bytes()) != parent["conformance_audit_sha256"]:
        raise RuntimeError("Parent conformance audit hash changed")
    audit = _object(audit_path)
    if not audit.get("all_gates_passed") or not audit.get(
        "causalds_oracle_development_eligible"
    ):
        raise RuntimeError("Parent conformance run did not authorize Oracle-development")
    if config["reasoner"] != parent_config["reasoner"]:
        raise RuntimeError("Oracle-development changed the frozen reasoner runtime")
    if config["evidence_contract"] != parent_config["evidence_contract"]:
        raise RuntimeError("Oracle-development changed the frozen evidence contract")
    parent_frozen = parent_config["frozen_inputs"]
    current_frozen = config["frozen_reasoner_inputs"]
    for key in ("prompt_contract", "prompt_contract_sha256", "prompt_bundle_sha256", "response_schemas"):
        if current_frozen[key] != parent_frozen[key]:
            raise RuntimeError(f"Oracle-development changed frozen reasoner input: {key}")
    if config_path != (PROJECT_ROOT / DEFAULT_CONFIG).resolve() and not config_path.is_file():
        raise RuntimeError("Oracle-development candidate path is invalid")


def _validate_benchmark(config: dict[str, Any]) -> tuple[tuple[str, ...], set[str]]:
    frozen = config["frozen_benchmark_inputs"]
    for path_key, hash_key in (
        ("split_manifest", "split_manifest_sha256"),
        ("task_manifest", "task_manifest_sha256"),
        ("oracle_loader_config", "oracle_loader_config_sha256"),
    ):
        if sha256_hex((PROJECT_ROOT / frozen[path_key]).read_bytes()) != frozen[hash_key]:
            raise RuntimeError(f"Frozen benchmark input hash changed: {path_key}")
    split = _object(PROJECT_ROOT / frozen["split_manifest"])
    cohort = split["cohorts"][frozen["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if dev_ids != tuple(frozen["scene_ids"]):
        raise RuntimeError("Frozen primary development scene IDs changed")
    if len(dev_ids) != frozen["scenes"] or set(dev_ids) & holdout_ids:
        raise RuntimeError("Oracle-development split invariant failed")
    task_rows = _rows(PROJECT_ROOT / frozen["task_manifest"])
    actual = {
        (row["scene_id"], row["task_id"])
        for row in task_rows
        if row["scene_id"] in dev_ids
    }
    expected = {(scene, task) for scene in dev_ids for task in TASKS}
    if actual != expected or len(expected) != frozen["expected_records"]:
        raise RuntimeError("Frozen Oracle-development task panel changed")
    return dev_ids, holdout_ids


def _decoding_config(
    reasoner: dict[str, Any], schema_path: Path, provider_schema: dict[str, Any]
) -> dict[str, Any]:
    return {
        "reasoning_effort": reasoner["reasoning_effort"],
        "sampling_temperature": reasoner["sampling_temperature"],
        "max_output_tokens": reasoner["max_output_tokens"],
        "max_validation_retries": reasoner["max_validation_retries"],
        "service_tier": reasoner["service_tier"],
        "store": reasoner["store"],
        "structured_outputs": reasoner["structured_outputs"],
        "response_schema_sha256": sha256_hex(schema_path.read_bytes()),
        "provider_response_schema_sha256": sha256_hex(
            canonical_json_bytes(provider_schema)
        ),
    }


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

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = _object(config_path, yaml_file=True)
    _validate_candidate(config_path, config)
    dev_ids, holdout_ids = _validate_benchmark(config)
    source_root = args.source_root.resolve()
    bundle, prompt_bundle_sha256 = _load_prompt_bundle(config)
    reasoner = config["reasoner"]
    frozen_reasoner = config["frozen_reasoner_inputs"]
    frozen_benchmark = config["frozen_benchmark_inputs"]

    provider_schemas: dict[str, dict[str, Any]] = {}
    schema_paths: dict[str, Path] = {}
    for task_id, item in frozen_reasoner["response_schemas"].items():
        path = PROJECT_ROOT / item["path"]
        if sha256_hex(path.read_bytes()) != item["sha256"]:
            raise RuntimeError(f"Frozen response schema hash changed: {task_id}")
        schema_paths[task_id] = path
        provider_schemas[task_id] = _provider_schema(_object(path))

    oracle_config_sha = frozen_benchmark["oracle_loader_config_sha256"]
    cases: list[dict[str, Any]] = []
    oracle_audit: list[dict[str, Any]] = []
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError("Oracle-development attempted holdout access")
        loaded = load_causalds_oracle_graph(
            source_root,
            scene_id,
            config_sha256=oracle_config_sha,
        )
        graph = loaded.graph_artifact
        if graph.graph_method != "oracle" or graph.graph_type != "dag":
            raise RuntimeError("Oracle-development requires a canonical Oracle DAG")
        oracle_audit.append(loaded.audit_record())
        for task_id in TASKS:
            query, variable_map, public_tasks_sha = load_reasoner_query(
                source_root, scene_id, task_id
            )
            if variable_map.mapping_sha256 != loaded.variable_map.mapping_sha256:
                raise RuntimeError("Oracle graph and query variable mappings disagree")
            graph_view = graph.reasoner_view()
            glossary = noncausal_glossary(variable_map)
            query_view = v2_query_view(query)
            prompt = bundle.render(
                task_id=task_id,
                graph_reasoner_view=graph_view,
                query_view=query_view,
                glossary=glossary,
            )
            if any(variable.public_name in prompt for variable in variable_map.variables):
                raise RuntimeError(f"Public semantic name leaked into prompt: {scene_id}")
            official = load_official_target(source_root, query, variable_map)
            graph_target = conservative_target(graph.partial_graph, query)
            cases.append(
                {
                    "case_id": f"{scene_id}:{task_id}",
                    "scene_id": scene_id,
                    "task_id": task_id,
                    "query": query,
                    "variable_map": variable_map,
                    "graph": graph,
                    "graph_view": graph_view,
                    "glossary": glossary,
                    "prompt": prompt,
                    "official": official,
                    "graph_target": graph_target,
                    "answer_class": _answer_class(task_id, official),
                    "required_empty_representation": _required_empty_representation(
                        task_id, official
                    ),
                    "public_tasks_sha256": public_tasks_sha,
                }
            )

    expected = config["preflight_expectations"]
    class_counts = Counter(case["answer_class"] for case in cases)
    target_mismatches = [
        {
            "case_id": case["case_id"],
            "official": list(case["official"].accepted),
            "graph_derived": case["graph_target"].to_dict(),
        }
        for case in cases
        if not _targets_equivalent(
            case["task_id"], case["official"], case["graph_target"]
        )
    ]
    target_matches = len(cases) - len(target_mismatches)
    required_empty = sum(
        case["required_empty_representation"] is not None for case in cases
    )
    if len(cases) != expected["rendered_prompts"]:
        raise RuntimeError("Oracle-development case count changed")
    if target_matches != expected["official_graph_target_matches"]:
        raise RuntimeError(
            "Official and graph-derived Oracle targets disagree: "
            + json.dumps(target_mismatches, sort_keys=True)
        )
    if dict(class_counts) != {
        key: value for key, value in expected["answer_classes"].items() if value
    }:
        raise RuntimeError("Oracle-development answer-class distribution changed")
    if required_empty != expected["required_empty_sentinel_records"]:
        raise RuntimeError("Oracle-development empty-sentinel distribution changed")

    outputs = config["outputs"]
    raw_path = PROJECT_ROOT / outputs["raw_log"]
    cache_path = PROJECT_ROOT / outputs["cache"]
    if (raw_path.exists() or cache_path.exists()) and not (
        args.resume or args.check or args.preflight
    ):
        raise FileExistsError("Existing Oracle-development run found; use --resume or --check")
    cache = CanonicalResponseCache.load(cache_path)
    raw_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if raw_path.exists():
        for row in _rows(raw_path):
            raw_history[row["cache_key"]].append(row)
    for history in raw_history.values():
        history.sort(key=lambda item: item["attempt"])

    for case in cases:
        task_id = case["task_id"]
        decoding = _decoding_config(
            reasoner, schema_paths[task_id], provider_schemas[task_id]
        )
        case["identity"] = build_cache_identity(
            model_version=reasoner["model_version"],
            prompt_template=bundle.template_for(task_id),
            graph_reasoner_view=case["graph_view"],
            query=case["query"],
            glossary=case["glossary"],
            decoding_config=decoding,
        )

    if args.preflight:
        cache_hits = sum(cache.get(case["identity"]) is not None for case in cases)
        print(
            json.dumps(
                {
                    "preflight_passed": True,
                    "candidate_id": config["candidate_id"],
                    "graph_condition": "G_ORACLE",
                    "scenes": len(dev_ids),
                    "tasks_per_scene": len(TASKS),
                    "records": len(cases),
                    "unique_rendered_prompts": len(
                        {sha256_hex(case["prompt"].encode("utf-8")) for case in cases}
                    ),
                    "official_graph_target_matches": target_matches,
                    "answer_class_counts": dict(sorted(class_counts.items())),
                    "required_empty_sentinel_records": required_empty,
                    "no_valid_adjustment_set_gate": "not_applicable_zero_targets",
                    "cpdag_uncertainty_gate": "not_applicable_oracle_is_dag",
                    "cached_records": cache_hits,
                    "planned_new_records": len(cases) - cache_hits,
                    "holdout_accessed": False,
                    "api_calls": 0,
                },
                indent=2,
            )
        )
        return 0

    if args.check and (not raw_path.exists() or not cache_path.exists()):
        raise FileNotFoundError("--check requires Oracle-development raw log and cache")
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
                response_schema_name=SCHEMA_NAMES[task_id],
                model_version=reasoner["model_version"],
                reasoning_effort=reasoner["reasoning_effort"],
                service_tier=reasoner["service_tier"],
                store=reasoner["store"],
                transport_max_retries=reasoner["transport_max_retries"],
                timeout_seconds=reasoner["timeout_seconds"],
                experiment_id="T12_v3_oracle_development",
            )
            if backend.sdk_version != reasoner["sdk_version"]:
                raise RuntimeError("OpenAI SDK version drift")
            backends[task_id] = backend

    records: list[dict[str, Any]] = []
    live_calls = 0
    for index, case in enumerate(cases, 1):
        identity = case["identity"]
        query: ReasonerQuery = case["query"]
        raw_text = cache.get(identity)
        was_cache_hit = raw_text is not None
        history = raw_history[identity.cache_key]
        parsed = None
        chosen_raw = next(
            (item for item in reversed(history) if item["validation_error"] is None),
            None,
        )
        if raw_text is None and chosen_raw is not None:
            parsed = parse_task_specific_response(chosen_raw["raw_text"], query)
            raw_text = chosen_raw["raw_text"]
            cache.put(identity, raw_text)
            cache.write(cache_path)
            was_cache_hit = True
        elif raw_text is not None:
            parsed = parse_task_specific_response(raw_text, query)
            if chosen_raw is None:
                raise RuntimeError(f"Cached response lacks raw audit: {case['case_id']}")
        elif args.check:
            raise RuntimeError(f"Missing cached response: {case['case_id']}")
        else:
            validation_error: str | None = (
                history[-1]["validation_error"] if history else None
            )
            start_attempt = len(history)
            for attempt in range(start_attempt, reasoner["max_validation_retries"] + 1):
                calls_so_far = [item for values in raw_history.values() for item in values]
                captured_cost = _cost(
                    calls_so_far,
                    config["budget"]["pricing_usd_per_million_tokens"],
                )["estimated_standard_cost_usd"]
                if captured_cost >= config["budget"]["captured_run_cost_stop_usd"]:
                    print(
                        json.dumps(
                            {
                                "partial": True,
                                "reason": "captured_run_cost_stop",
                                "estimated_standard_cost_usd": captured_cost,
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
                    "schema_version": "fourgraph.t12_v3_oracle_development_raw_call.v1",
                    "cache_key": identity.cache_key,
                    "case_id": case["case_id"],
                    "scene_id": case["scene_id"],
                    "task_id": case["task_id"],
                    "graph_condition": "G_ORACLE",
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
                _append_raw(raw_path, raw_record)
                history.append(raw_record)
                if parsed is not None:
                    raw_text = response.raw_text
                    chosen_raw = raw_record
                    cache.put(identity, raw_text)
                    cache.write(cache_path)
                    break
            if parsed is None or raw_text is None or chosen_raw is None:
                raise RuntimeError(
                    f"Oracle-development response failed validation: {case['case_id']}"
                )

        scores = score_answer(parsed, case["official"], case["graph_target"])
        first_valid = bool(history and history[0]["validation_error"] is None)
        record = {
            "scene_id": case["scene_id"],
            "task_id": case["task_id"],
            "graph_condition": "G_ORACLE",
            "graph_type": case["graph"].graph_type,
            "graph_view": case["graph"].graph_view,
            "graph_sha256": case["graph"].graph_sha256,
            "graph_artifact_sha256": case["graph"].artifact_sha256,
            "variable_mapping_sha256": case["variable_map"].mapping_sha256,
            "query_sha256": case["query"].sha256,
            "public_tasks_sha256": case["public_tasks_sha256"],
            "prompt_bundle_sha256": prompt_bundle_sha256,
            "prompt_sha256": sha256_hex(case["prompt"].encode("utf-8")),
            "cache_key": identity.cache_key,
            "raw_response_sha256": sha256_hex(raw_text.encode("utf-8")),
            "parsed_response": parsed.to_dict(),
            "official_target": list(case["official"].accepted),
            "official_ground_truth_sha256": case["official"].ground_truth_sha256,
            "graph_derived_target": case["graph_target"].to_dict(),
            "answer_class": case["answer_class"],
            "required_empty_representation": case["required_empty_representation"],
            **scores,
            "schema_version": "fourgraph.t12_v3_oracle_development_score.v1",
            "first_attempt_schema_compliant": first_valid,
            "attempts": len(history),
            "request_id": chosen_raw["request_id"],
            "provider": chosen_raw["provider"],
            "model_version": chosen_raw["model_version"],
            "input_tokens": chosen_raw["input_tokens"],
            "cached_input_tokens": chosen_raw["cached_input_tokens"],
            "output_tokens": chosen_raw["output_tokens"],
            "reasoning_tokens": chosen_raw["reasoning_tokens"],
            "latency_ms": chosen_raw["latency_ms"],
        }
        records.append(record)
        print(
            json.dumps(
                {
                    "record": index,
                    "case_id": case["case_id"],
                    "mode": "cache" if was_cache_hit else "live",
                    "oracle_answer_accuracy": scores["oracle_answer_accuracy"],
                }
            ),
            flush=True,
        )
        if args.call_limit is not None and live_calls >= args.call_limit:
            print(json.dumps({"partial": True, "live_calls": live_calls}))
            return 0

    selected_keys = {record["cache_key"] for record in records}
    services = [item for key in selected_keys for item in raw_history[key]]
    usage = _cost(services, config["budget"]["pricing_usd_per_million_tokens"])
    correct = sum(record["oracle_answer_accuracy"] for record in records)
    task_correct = {
        task: sum(
            record["oracle_answer_accuracy"]
            for record in records
            if record["task_id"] == task
        )
        for task in TASKS
    }
    empty_records = [
        record for record in records if record["required_empty_representation"]
    ]
    empty_correct = sum(record["oracle_answer_accuracy"] for record in empty_records)
    representation_groups = {
        representation: [
            record
            for record in empty_records
            if record["required_empty_representation"] == representation
        ]
        for representation in sorted(
            {record["required_empty_representation"] for record in empty_records}
        )
    }
    gates = config["oracle_development_gate"]
    gate_results = {
        "final_parse_success": len(records) == gates["final_parse_success_count"],
        "oracle_answer_accuracy": correct >= gates["oracle_answer_accuracy_min_count"],
        "per_task_accuracy": all(
            value >= gates["per_task_accuracy_min_count"]
            for value in task_correct.values()
        ),
        "empty_sentinel_accuracy": empty_correct
        >= gates["empty_sentinel_accuracy_min_count"],
        "each_present_empty_representation_has_correct_answer": all(
            any(record["oracle_answer_accuracy"] for record in group)
            for group in representation_groups.values()
        ),
        "model_snapshot_match": all(
            record["model_version"] == reasoner["model_version"]
            for record in records
        ),
        "usage_present": all(
            record["input_tokens"] is not None
            and record["output_tokens"] is not None
            and record["reasoning_tokens"] is not None
            for record in records
        ),
        "holdout_not_accessed": True,
    }
    record_payload = b"".join(
        canonical_json_bytes(record, newline=True) for record in records
    )
    output_values = [int(item["output_tokens"]) for item in services]
    reasoning_values = [int(item["reasoning_tokens"]) for item in services]
    latency_values = [int(item["latency_ms"]) for item in services]
    audit = {
        "schema_version": "fourgraph.t12_v3_oracle_development_audit.v1",
        "candidate_id": config["candidate_id"],
        "config_sha256": sha256_hex(config_path.read_bytes()),
        "runner_sha256": sha256_hex(Path(__file__).read_bytes()),
        "parent_conformance_audit_sha256": config["parent_candidate"][
            "conformance_audit_sha256"
        ],
        "provider": reasoner["provider"],
        "model_id": reasoner["model_id"],
        "model_version": reasoner["model_version"],
        "reasoning_effort": reasoner["reasoning_effort"],
        "max_output_tokens": reasoner["max_output_tokens"],
        "graph_condition": "G_ORACLE",
        "development_scenes": len(dev_ids),
        "tasks_per_scene": len(TASKS),
        "records": len(records),
        "oracle_answer_correct": correct,
        "oracle_answer_accuracy": _rate(correct, len(records)),
        "uncertainty_aware_correct": sum(
            record["uncertainty_aware_correctness"] for record in records
        ),
        "task_correct": task_correct,
        "task_accuracy": {
            task: _rate(value, len(dev_ids)) for task, value in task_correct.items()
        },
        "answer_class_counts": dict(sorted(class_counts.items())),
        "required_empty_sentinel_records": len(empty_records),
        "required_empty_sentinel_correct": empty_correct,
        "required_empty_sentinel_accuracy": _rate(empty_correct, len(empty_records)),
        "empty_representation_results": {
            key: {
                "records": len(group),
                "correct": sum(record["oracle_answer_accuracy"] for record in group),
            }
            for key, group in representation_groups.items()
        },
        "no_valid_adjustment_set_gate": "not_applicable_zero_targets",
        "cpdag_uncertainty_gate": "not_applicable_oracle_is_dag",
        "first_attempt_schema_compliance": sum(
            record["first_attempt_schema_compliant"] for record in records
        ),
        "captured_calls": len(services),
        "retry_calls": sum(max(0, record["attempts"] - 1) for record in records),
        "completed_calls": sum(
            item["response_status"] == "completed" for item in services
        ),
        "incomplete_calls": sum(
            item["response_status"] == "incomplete" for item in services
        ),
        "max_output_token_utilization": round(
            max(output_values) / reasoner["max_output_tokens"], 8
        ),
        "reasoning_tokens_distribution": {
            "min": min(reasoning_values),
            "median": _median(reasoning_values),
            "max": max(reasoning_values),
        },
        "latency_ms_distribution": {
            "min": min(latency_values),
            "median": _median(latency_values),
            "max": max(latency_values),
        },
        "usage": usage,
        "gate_thresholds": gates,
        "gate_results": gate_results,
        "oracle_development_passed": all(gate_results.values()),
        "full_development_matrix_eligible": all(gate_results.values()),
        "holdout_reasoner_ready": False,
        "holdout_accessed": False,
        "oracle_input_audit": oracle_audit,
        "records_sha256": sha256_hex(record_payload),
        "raw_log_sha256": sha256_hex(raw_path.read_bytes()),
        "cache_sha256": sha256_hex(cache_path.read_bytes()),
    }
    audit_payload = canonical_json_bytes(audit, newline=True)
    records_path = PROJECT_ROOT / outputs["records"]
    audit_path = PROJECT_ROOT / outputs["audit"]
    if args.check:
        if records_path.read_bytes() != record_payload:
            raise RuntimeError("Oracle-development scores do not reproduce byte-for-byte")
        if audit_path.read_bytes() != audit_payload:
            raise RuntimeError("Oracle-development audit does not reproduce byte-for-byte")
    else:
        records_path.parent.mkdir(parents=True, exist_ok=True)
        records_path.write_bytes(record_payload)
        audit_path.write_bytes(audit_payload)
    print(json.dumps({**audit, "live_calls_this_run": live_calls}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
