"""Run/replay the frozen GPT-5.4 Mini T12 v2 conformance candidate."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.conformance_audit import semantic_equivalent  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.llm_backend import LLMCallRequest  # noqa: E402
from fourgraph.reasoner import ReasonerQuery, _canonical_answer  # noqa: E402
from fourgraph.reasoner_v2 import (  # noqa: E402
    CanonicalResponseCache,
    build_cache_identity,
    parse_task_specific_response,
)
from fourgraph.reasoner_v3 import PromptV3Bundle  # noqa: E402
from fourgraph.t12_openai_backend import T12OpenAIResponsesBackend  # noqa: E402


DEFAULT_CONFIG = Path("configs/t12_v2_openai_mini.yaml")
SCHEMA_NAMES = {
    "identification__one_valid_adjustment_set": "t12_v2_one_valid_adjustment_set",
    "identification__all_minimal_adjustment_sets": "t12_v2_all_minimal_adjustment_sets",
    "identification__minimal_adjustment_set_size": "t12_v2_minimal_adjustment_set_size",
    "identification__n_valid_adjustment_sets": "t12_v2_n_valid_adjustment_sets",
    "bias_diagnostic__forbidden_controls_list": "t12_v2_forbidden_controls_list",
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


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Translate the frozen contract to OpenAI's equivalent strict subset."""

    def translate(value: Any) -> Any:
        if isinstance(value, list):
            return [translate(item) for item in value]
        if not isinstance(value, dict):
            return value
        translated: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"$schema", "pattern", "uniqueItems", "minimum"}:
                continue
            # OpenAI strict Structured Outputs supports anyOf, while rejecting
            # oneOf and several validation-only constraints used by our local
            # contract. The task shape is unchanged and local parsing remains
            # authoritative for IDs, uniqueness, and non-negative counts.
            target = "anyOf" if key == "oneOf" else key
            translated[target] = translate(item)
        return translated

    return translate(schema)


def _render(template: str, row: dict[str, Any]) -> str:
    values = {
        "{{GRAPH_JSON}}": canonical_json_bytes(row["graph"]).decode("utf-8"),
        "{{QUERY_JSON}}": canonical_json_bytes(row["query"]).decode("utf-8"),
        "{{GLOSSARY_JSON}}": canonical_json_bytes(row["glossary"]).decode("utf-8"),
    }
    prompt = template
    for marker, value in values.items():
        if prompt.count(marker) != 1:
            raise ValueError(f"Prompt marker must occur exactly once: {marker}")
        prompt = prompt.replace(marker, value)
    return prompt


def _query(row: dict[str, Any]) -> ReasonerQuery:
    value = row["query"]
    return ReasonerQuery(
        scene_id=row["case_id"],
        task_id=value["task_id"],
        treatment=value["treatment"],
        outcome=value["outcome"],
        candidate_variables=tuple(value["candidate_variables"]),
        response_field=value["response_field"],
    )


def _strict_correct(parsed: Any, row: dict[str, Any]) -> bool:
    expected = row["expected"]
    if parsed.status != expected["status"]:
        return False
    if parsed.status == "undetermined":
        return parsed.answer == "undetermined"
    accepted = tuple(
        _canonical_answer(row["task_id"], item) for item in expected["accepted"]
    )
    return parsed.answer in accepted


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
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def _cost(records: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, Any]:
    input_tokens = sum(int(item.get("input_tokens") or 0) for item in records)
    cached = sum(int(item.get("cached_input_tokens") or 0) for item in records)
    output = sum(int(item.get("output_tokens") or 0) for item in records)
    reasoning = sum(int(item.get("reasoning_tokens") or 0) for item in records)
    uncached = input_tokens - cached
    estimated = (
        uncached * prices["uncached_input"]
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


def _write_failed_smoke_audit(
    *,
    config: dict[str, Any],
    config_path: Path,
    suite_path: Path,
    prompt_sha256: str,
    raw_path: Path,
    cache_path: Path,
    raw_history: dict[str, list[dict[str, Any]]],
    planned_rows: list[dict[str, Any]],
    failed_row: dict[str, Any],
    failed_cache_key: str,
    cache_hits: int,
    check: bool,
) -> dict[str, Any]:
    reasoner = config["reasoner"]
    outputs = config["outputs"]
    calls = [item for history in raw_history.values() for item in history]
    failed_calls = raw_history[failed_cache_key]
    model_match = bool(calls) and all(
        item["model_version"] == reasoner["model_version"] for item in calls
    )
    usage_present = bool(calls) and all(
        item.get("input_tokens") is not None
        and item.get("output_tokens") is not None
        and item.get("reasoning_tokens") is not None
        for item in calls
    )
    audit = {
        "schema_version": (
            "fourgraph.t12_v3_openai_smoke_audit.v1"
            if config["schema_version"].startswith("fourgraph.t12_v3")
            else "fourgraph.t12_v2_openai_smoke_audit.v1"
        ),
        "provider": reasoner["provider"],
        "model_id": reasoner["model_id"],
        "model_version": reasoner["model_version"],
        "reasoning_effort": reasoner["reasoning_effort"],
        "max_output_tokens": reasoner["max_output_tokens"],
        "planned_cases": len(planned_rows),
        "planned_case_ids": [row["case_id"] for row in planned_rows],
        "valid_cases_before_stop": sum(
            1
            for history in raw_history.values()
            if any(item["validation_error"] is None for item in history)
        ),
        "failed_case_id": failed_row["case_id"],
        "failed_case_attempts": len(failed_calls),
        "failed_attempt_statuses": [
            {
                "attempt": item["attempt"],
                "response_status": item["response_status"],
                "incomplete_reason": item["incomplete_reason"],
                "output_tokens": item["output_tokens"],
                "reasoning_tokens": item["reasoning_tokens"],
                "visible_output_characters": len(item["raw_text"]),
            }
            for item in failed_calls
        ],
        "failure_class": "reasoning_budget_exhausted_before_visible_structured_output",
        "usage": _cost(
            calls, config["budget"]["pricing_usd_per_million_tokens"]
        ),
        "cache_hits_during_audit_replay": cache_hits,
        "technical_gate_results": {
            "parsed_10_of_10": False,
            "model_snapshot_match": model_match,
            "usage_and_reasoning_tokens_recorded": usage_present,
            "cache_resume_operational": cache_hits > 0,
            "holdout_not_accessed": True,
        },
        "smoke_technical_passed": False,
        "scientific_gate_applied": False,
        "conformance_150_started": False,
        "causalds_oracle_development_eligible": False,
        "full_development_matrix_eligible": False,
        "holdout_accessed": False,
        "required_action": (
            "Do not run 150-case conformance under this frozen "
            f"{reasoner['max_output_tokens']}-token "
            "candidate; pre-register a separate candidate if the reasoning "
            "budget or effort is changed."
        ),
        "config_sha256": sha256_hex(config_path.read_bytes()),
        "suite_sha256": sha256_hex(suite_path.read_bytes()),
        "prompt_sha256": prompt_sha256,
        "raw_log_sha256": sha256_hex(raw_path.read_bytes()),
        "cache_sha256": sha256_hex(cache_path.read_bytes()),
    }
    target = PROJECT_ROOT / outputs["smoke_audit"]
    payload = canonical_json_bytes(audit, newline=True)
    if check:
        if not target.exists() or target.read_bytes() != payload:
            raise RuntimeError("Failed smoke audit does not reproduce byte-for-byte")
    else:
        target.write_bytes(payload)
    return audit


def main(default_config: Path = DEFAULT_CONFIG) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=default_config)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--call-limit", type=int)
    args = parser.parse_args()
    if args.smoke and args.call_limit is not None and args.call_limit > 10:
        raise ValueError("Smoke mode cannot exceed ten live calls")

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = _object(config_path, yaml_file=True)
    is_v3 = config["schema_version"].startswith("fourgraph.t12_v3")
    if is_v3:
        execution = config["live_execution"]
        if not execution.get("allowed"):
            raise ValueError("Frozen T12 v3 candidate does not allow live execution")
        if not args.smoke and (
            execution.get("next_action") != "full_150_conformance"
            or not execution.get("conformance_auto_start_allowed")
        ):
            raise ValueError(
                "Frozen T12 v3 candidate currently authorizes only the ten-case smoke"
            )
        parent = config.get("parent_candidate", {})
        if "config_sha256" in parent:
            parent_path = PROJECT_ROOT / parent["config"]
            smoke_audit_path = PROJECT_ROOT / parent["smoke_audit"]
            if sha256_hex(parent_path.read_bytes()) != parent["config_sha256"]:
                raise RuntimeError("Frozen v3 smoke-parent config hash changed")
            if sha256_hex(smoke_audit_path.read_bytes()) != parent["smoke_audit_sha256"]:
                raise RuntimeError("Frozen v3 smoke audit hash changed")
            parent_config = _object(parent_path, yaml_file=True)
            smoke_audit = _json_object(smoke_audit_path)
            if not smoke_audit["smoke_technical_passed"]:
                raise RuntimeError("V3 full conformance requires a passed parent smoke")
            for field in ("reasoner", "evidence_contract", "frozen_inputs"):
                if config[field] != parent_config[field]:
                    raise RuntimeError(f"V3 full candidate changed frozen field: {field}")
            if config["calibration"]["prospective_gates"] != parent_config["calibration"]["prospective_gates"]:
                raise RuntimeError("V3 full candidate changed prospective gates")
    frozen = config["frozen_inputs"]
    reasoner = config["reasoner"]
    outputs = config["outputs"]
    suite_path = PROJECT_ROOT / frozen["suite"]
    if sha256_hex(suite_path.read_bytes()) != frozen["suite_sha256"]:
        raise RuntimeError("Frozen conformance suite hash changed")
    if is_v3:
        prompt_contract_path = PROJECT_ROOT / frozen["prompt_contract"]
        if sha256_hex(prompt_contract_path.read_bytes()) != frozen["prompt_contract_sha256"]:
            raise RuntimeError("Frozen v3 prompt contract hash changed")
        prompt_contract = _json_object(prompt_contract_path)
        if prompt_contract["prompt_components"]["bundle_sha256"] != frozen["prompt_bundle_sha256"]:
            raise RuntimeError("Frozen v3 prompt bundle hash changed")
        prompt_config = _object(PROJECT_ROOT / "configs/t12_v3_prompt.yaml", yaml_file=True)
        prompt_bundle = PromptV3Bundle.load(
            base_path=PROJECT_ROOT / prompt_config["prompt_bundle"]["base"],
            module_paths={
                task: PROJECT_ROOT / path
                for task, path in prompt_config["prompt_bundle"]["modules"].items()
            },
        )
        components = prompt_contract["prompt_components"]
        if sha256_hex(prompt_bundle.base_template.encode("utf-8")) != components["base"]["sha256"]:
            raise RuntimeError("Frozen v3 base prompt hash changed")
        for task_id, module in prompt_bundle.modules.items():
            expected_component = components["modules"][task_id]
            if sha256_hex(module.encode("utf-8")) != expected_component["sha256"]:
                raise RuntimeError(f"Frozen v3 module hash changed: {task_id}")
            if sha256_hex(prompt_bundle.template_for(task_id).encode("utf-8")) != expected_component["assembled_template_sha256"]:
                raise RuntimeError(f"Frozen v3 assembled prompt hash changed: {task_id}")
        prompt_sha256 = components["bundle_sha256"]
        measurement_path = PROJECT_ROOT / frozen["measurement_audit"]
        if sha256_hex(measurement_path.read_bytes()) != frozen["measurement_audit_sha256"]:
            raise RuntimeError("Frozen v3 measurement audit hash changed")
        for path_key, hash_key in (
            ("manual_review_panel", "manual_review_panel_sha256"),
            ("smoke_manifest", "smoke_manifest_sha256"),
        ):
            if sha256_hex((PROJECT_ROOT / frozen[path_key]).read_bytes()) != frozen[hash_key]:
                raise RuntimeError(f"Frozen v3 {path_key} hash changed")
    else:
        prompt_path = PROJECT_ROOT / frozen["prompt"]
        if sha256_hex(prompt_path.read_bytes()) != frozen["prompt_sha256"]:
            raise RuntimeError("Frozen v2 prompt hash changed")
        prompt_template_v2 = prompt_path.read_text(encoding="utf-8")
        prompt_sha256 = frozen["prompt_sha256"]
        measurement_path = PROJECT_ROOT / config["measurement_audit"]["audit"]
    measurement = _json_object(measurement_path)
    if not measurement["measurement_ready_for_model_screening"]:
        raise RuntimeError("Measurement audit is not ready")

    rows = [
        json.loads(line)
        for line in suite_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if len(rows) != frozen["cases"] or any(
        row["uses_causalds_story"] or row["uses_causalds_answer"] for row in rows
    ):
        raise RuntimeError("Conformance-suite evidence invariant failed")
    if args.smoke:
        smoke = _json_object(
            PROJECT_ROOT
            / (frozen["smoke_manifest"] if is_v3 else config["smoke"]["manifest"])
        )
        smoke_ids = smoke["case_ids"]
        rows_by_id = {row["case_id"]: row for row in rows}
        rows = [rows_by_id[case_id] for case_id in smoke_ids]
        if len(rows) != config["smoke"]["cases"]:
            raise RuntimeError("Frozen smoke manifest count changed")

    raw_path = PROJECT_ROOT / outputs["raw_log"]
    cache_path = PROJECT_ROOT / outputs["cache"]
    if (raw_path.exists() or cache_path.exists()) and not (
        args.resume or args.check or args.preflight
    ):
        raise FileExistsError("Existing OpenAI candidate run found; use --resume or --check")
    cache = CanonicalResponseCache.load(cache_path)
    raw_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if raw_path.exists():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line:
                item = json.loads(line)
                raw_history[item["cache_key"]].append(item)

    schemas: dict[str, dict[str, Any]] = {}
    backends: dict[str, T12OpenAIResponsesBackend] = {}
    if not (args.check or args.preflight):
        load_dotenv((PROJECT_ROOT / args.dotenv).resolve(), override=True)
        api_key = os.environ.get(reasoner["credential_env"], "")
    else:
        api_key = ""
    for task_id, schema_entry in frozen["response_schemas"].items():
        relative = schema_entry["path"] if is_v3 else schema_entry
        schema_path = PROJECT_ROOT / relative
        if is_v3 and sha256_hex(schema_path.read_bytes()) != schema_entry["sha256"]:
            raise RuntimeError(f"Frozen v3 response schema hash changed: {task_id}")
        schema = _json_object(schema_path)
        schemas[task_id] = _provider_schema(schema)
        if not (args.check or args.preflight):
            backend = T12OpenAIResponsesBackend(
                api_key=api_key,
                response_schema=schemas[task_id],
                response_schema_name=(
                    SCHEMA_NAMES[task_id].replace("t12_v2_", "t12_v3_")
                    if is_v3
                    else SCHEMA_NAMES[task_id]
                ),
                model_version=reasoner["model_version"],
                reasoning_effort=reasoner["reasoning_effort"],
                service_tier=reasoner["service_tier"],
                store=reasoner["store"],
                transport_max_retries=reasoner["transport_max_retries"],
                timeout_seconds=reasoner["timeout_seconds"],
                experiment_id=(
                    "T12_v3_conformance_smoke"
                    if is_v3
                    else "T12_v2_conformance"
                ),
            )
            if backend.sdk_version != reasoner["sdk_version"]:
                raise RuntimeError(
                    f"openai SDK drift: expected={reasoner['sdk_version']}, actual={backend.sdk_version}"
                )
            backends[task_id] = backend

    if args.preflight:
        rendered_hashes = []
        cached_cases = 0
        for row in rows:
            query = _query(row)
            template = (
                prompt_bundle.template_for(row["task_id"])
                if is_v3
                else prompt_template_v2
            )
            rendered = _render(template, row)
            parse_task_specific_response(
                canonical_json_bytes(row["expected_response"]).decode("utf-8"),
                query,
            )
            rendered_hashes.append(sha256_hex(rendered.encode("utf-8")))
            schema_path = PROJECT_ROOT / row["response_schema"]
            decoding = {
                "reasoning_effort": reasoner["reasoning_effort"],
                "sampling_temperature": reasoner["sampling_temperature"],
                "max_output_tokens": reasoner["max_output_tokens"],
                "max_validation_retries": reasoner["max_validation_retries"],
                "service_tier": reasoner["service_tier"],
                "store": reasoner["store"],
                "structured_outputs": reasoner["structured_outputs"],
                "response_schema_sha256": sha256_hex(schema_path.read_bytes()),
                "provider_response_schema_sha256": sha256_hex(
                    canonical_json_bytes(schemas[row["task_id"]])
                ),
            }
            identity = build_cache_identity(
                model_version=reasoner["model_version"],
                prompt_template=template,
                graph_reasoner_view=row["graph"],
                query=query,
                glossary=row["glossary"],
                decoding_config=decoding,
            )
            cached_cases += cache.get(identity) is not None
        print(
            json.dumps(
                {
                    "preflight_passed": True,
                    "candidate_id": config.get("candidate_id"),
                    "cases": len(rows),
                    "cached_cases": cached_cases,
                    "planned_new_cases": len(rows) - cached_cases,
                    "unique_rendered_prompts": len(set(rendered_hashes)),
                    "prompt_bundle_sha256": prompt_sha256,
                    "suite_sha256": sha256_hex(suite_path.read_bytes()),
                    "holdout_accessed": False,
                    "api_calls": 0,
                },
                indent=2,
            )
        )
        return 0

    records: list[dict[str, Any]] = []
    live_calls = 0
    cache_hits = 0

    for index, row in enumerate(rows, 1):
        query = _query(row)
        template = (
            prompt_bundle.template_for(row["task_id"])
            if is_v3
            else prompt_template_v2
        )
        prompt = _render(template, row)
        schema_path = PROJECT_ROOT / row["response_schema"]
        decoding = {
            "reasoning_effort": reasoner["reasoning_effort"],
            "sampling_temperature": reasoner["sampling_temperature"],
            "max_output_tokens": reasoner["max_output_tokens"],
            "max_validation_retries": reasoner["max_validation_retries"],
            "service_tier": reasoner["service_tier"],
            "store": reasoner["store"],
            "structured_outputs": reasoner["structured_outputs"],
            "response_schema_sha256": sha256_hex(schema_path.read_bytes()),
            "provider_response_schema_sha256": sha256_hex(
                canonical_json_bytes(schemas[row["task_id"]])
            ),
        }
        identity = build_cache_identity(
            model_version=reasoner["model_version"],
            prompt_template=template,
            graph_reasoner_view=row["graph"],
            query=query,
            glossary=row["glossary"],
            decoding_config=decoding,
        )
        raw_text = cache.get(identity)
        was_cache_hit = raw_text is not None
        parsed = None
        chosen_raw: dict[str, Any] | None = None
        history = raw_history.get(identity.cache_key, [])
        exhausted = (
            raw_text is None
            and len(history) >= reasoner["max_validation_retries"] + 1
            and not any(item["validation_error"] is None for item in history)
        )
        if exhausted and args.smoke:
            audit = _write_failed_smoke_audit(
                config=config,
                config_path=config_path,
                suite_path=suite_path,
                prompt_sha256=prompt_sha256,
                raw_path=raw_path,
                cache_path=cache_path,
                raw_history=raw_history,
                planned_rows=rows,
                failed_row=row,
                failed_cache_key=identity.cache_key,
                cache_hits=cache_hits,
                check=args.check,
            )
            print(json.dumps(audit, indent=2))
            return 0 if args.check else 2
        if raw_text is not None:
            cache_hits += 1
            parsed = parse_task_specific_response(raw_text, query)
            chosen_raw = next(
                (item for item in reversed(history) if item["validation_error"] is None),
                None,
            )
            if chosen_raw is None:
                raise RuntimeError(f"Cached response lacks auditable raw call: {row['case_id']}")
        elif args.check:
            raise RuntimeError(f"Missing cached response in --check: {row['case_id']}")
        else:
            validation_error = None
            for attempt in range(reasoner["max_validation_retries"] + 1):
                cost_stop = config.get("budget", {}).get("captured_run_cost_stop_usd")
                if cost_stop is not None:
                    calls_so_far = [
                        item
                        for call_history in raw_history.values()
                        for item in call_history
                    ]
                    captured_cost = _cost(
                        calls_so_far,
                        config["budget"]["pricing_usd_per_million_tokens"],
                    )["estimated_standard_cost_usd"]
                    if captured_cost >= cost_stop:
                        print(
                            json.dumps(
                                {
                                    "partial": True,
                                    "reason": "captured_run_cost_stop",
                                    "estimated_standard_cost_usd": captured_cost,
                                    "limit_usd": cost_stop,
                                    "live_calls": live_calls,
                                    "holdout_accessed": False,
                                }
                            )
                        )
                        return 3
                call_prompt = prompt
                if validation_error is not None:
                    call_prompt += (
                        "\n\nYour previous output violated the response contract: "
                        f"{validation_error}. Return only the required one-field JSON object."
                    )
                request = LLMCallRequest(
                    scene_id=row["case_id"],
                    attempt=attempt,
                    prompt=call_prompt,
                    provider=reasoner["provider"],
                    model_id=reasoner["model_id"],
                    model_version=reasoner["model_version"],
                    temperature=0,
                    max_tokens=reasoner["max_output_tokens"],
                    seed=None,
                )
                response = backends[row["task_id"]].complete(request)
                live_calls += 1
                try:
                    parsed = parse_task_specific_response(response.raw_text, query)
                    validation_error = None
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    validation_error = str(exc)
                raw_record = {
                    "schema_version": (
                        "fourgraph.t12_v3_openai_raw_call.v1"
                        if is_v3
                        else "fourgraph.t12_v2_openai_raw_call.v1"
                    ),
                    "cache_key": identity.cache_key,
                    "case_id": row["case_id"],
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
                raw_history[identity.cache_key].append(raw_record)
                if parsed is not None:
                    raw_text = response.raw_text
                    chosen_raw = raw_record
                    cache.put(identity, raw_text)
                    cache.write(cache_path)
                    break
            if parsed is None or raw_text is None or chosen_raw is None:
                if args.smoke:
                    audit = _write_failed_smoke_audit(
                        config=config,
                        config_path=config_path,
                        suite_path=suite_path,
                        prompt_sha256=prompt_sha256,
                        raw_path=raw_path,
                        cache_path=cache_path,
                        raw_history=raw_history,
                        planned_rows=rows,
                        failed_row=row,
                        failed_cache_key=identity.cache_key,
                        cache_hits=cache_hits,
                        check=args.check,
                    )
                    print(json.dumps(audit, indent=2))
                    return 0 if args.check else 2
                raise RuntimeError(
                    f"GPT-5.4 Mini failed response validation: {row['case_id']}"
                )

        history = raw_history[identity.cache_key]
        first_valid = bool(history and history[0]["validation_error"] is None)
        strict = _strict_correct(parsed, row)
        semantic = semantic_equivalent(
            task_id=row["task_id"],
            parsed_status=parsed.status,
            parsed_answer=parsed.answer,
            expected=row["expected"],
        )
        score_record = {
                "schema_version": (
                    "fourgraph.t12_v3_openai_conformance_score.v1"
                    if is_v3
                    else "fourgraph.t12_v2_openai_conformance_score.v1"
                ),
                "case_id": row["case_id"],
                "task_id": row["task_id"],
                "bucket": row["bucket"],
                "feature_tags": row["feature_tags"],
                "cache_key": identity.cache_key,
                "prompt_sha256": sha256_hex(prompt.encode("utf-8")),
                "raw_response_sha256": sha256_hex(raw_text.encode("utf-8")),
                "parsed_response": parsed.to_dict(),
                "expected": row["expected"],
                "strict_correct": strict,
                "semantic_equivalent_correct": semantic,
                "first_attempt_schema_compliant": first_valid,
                "attempts": len(history),
                "request_id": chosen_raw["request_id"],
                "model_version": chosen_raw["model_version"],
                "input_tokens": chosen_raw["input_tokens"],
                "cached_input_tokens": chosen_raw["cached_input_tokens"],
                "output_tokens": chosen_raw["output_tokens"],
                "reasoning_tokens": chosen_raw["reasoning_tokens"],
                "latency_ms": chosen_raw["latency_ms"],
            }
        if is_v3:
            score_record["answer_class"] = row["answer_class"]
        records.append(score_record)
        print(
            json.dumps(
                {
                    "case": index,
                    "case_id": row["case_id"],
                    "mode": "cache" if was_cache_hit else "live",
                    "strict_correct": strict,
                }
            ),
            flush=True,
        )
        if args.call_limit is not None and live_calls >= args.call_limit:
            print(json.dumps({"partial": True, "live_calls": live_calls}))
            return 0

    selected_cache_keys = {record["cache_key"] for record in records}
    services = [
        item
        for cache_key in selected_cache_keys
        for item in raw_history[cache_key]
    ]
    usage = _cost(
        services,
        config["budget"]["pricing_usd_per_million_tokens"],
    )
    common = {
        "provider": reasoner["provider"],
        "model_id": reasoner["model_id"],
        "model_version": reasoner["model_version"],
        "reasoning_effort": reasoner["reasoning_effort"],
        "max_output_tokens": reasoner["max_output_tokens"],
        "cases": len(records),
        "usage": usage,
        "config_sha256": sha256_hex(config_path.read_bytes()),
        "suite_sha256": sha256_hex(suite_path.read_bytes()),
        "prompt_sha256": prompt_sha256,
        "raw_log_sha256": sha256_hex(raw_path.read_bytes()),
        "cache_sha256": sha256_hex(cache_path.read_bytes()),
        "holdout_accessed": False,
    }
    if args.smoke:
        reasoning_values = [
            int(item["reasoning_tokens"])
            for item in records
            if item["reasoning_tokens"] is not None
        ]
        latency_values = [
            int(item["latency_ms"])
            for item in records
            if item["latency_ms"] is not None
        ]
        # Headroom is an engineering property of every billed provider call,
        # not only the eventually accepted response for each case. Otherwise
        # an incomplete max-token attempt could be hidden by a successful retry.
        output_values = [
            int(item["output_tokens"])
            for item in services
            if item["output_tokens"] is not None
        ]
        max_output_utilization = round(
            max(output_values) / reasoner["max_output_tokens"], 8
        )
        technical = {
            "parsed": len(records) == config["smoke"]["technical_gate"]["parsed"],
            "model_snapshot_match": all(
                item["model_version"] == reasoner["model_version"] for item in records
            ),
            "usage_present": all(
                item["input_tokens"] is not None
                and item["output_tokens"] is not None
                and item["reasoning_tokens"] is not None
                for item in records
            ),
            "holdout_not_accessed": True,
        }
        if is_v3:
            technical["first_attempt_schema_valid"] = all(
                item["first_attempt_schema_compliant"] for item in records
            )
        utilization_limit = config["smoke"]["technical_gate"].get(
            "max_output_token_utilization_max"
        )
        if utilization_limit is not None:
            technical["max_output_token_utilization"] = (
                max_output_utilization <= utilization_limit
            )
        audit = {
            "schema_version": (
                "fourgraph.t12_v3_openai_smoke_audit.v1"
                if is_v3
                else "fourgraph.t12_v2_openai_smoke_audit.v1"
            ),
            **common,
            "case_ids": [item["case_id"] for item in records],
            "captured_calls": len(services),
            "retry_calls": sum(
                max(0, int(item["attempts"]) - 1) for item in records
            ),
            "strict_accuracy_diagnostic_only": _rate(
                sum(item["strict_correct"] for item in records), len(records)
            ),
            "max_output_token_utilization": max_output_utilization,
            "max_output_token_utilization_gate": utilization_limit,
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
            "case_results": [
                {
                    "case_id": item["case_id"],
                    "task_id": item["task_id"],
                    "bucket": item["bucket"],
                    "strict_correct": item["strict_correct"],
                    "attempts": item["attempts"],
                    "reasoning_tokens": item["reasoning_tokens"],
                    "output_tokens": item["output_tokens"],
                    "latency_ms": item["latency_ms"],
                }
                for item in records
            ],
            "technical_gate_results": technical,
            "smoke_technical_passed": all(technical.values()),
            "scientific_gate_applied": False,
        }
        target = PROJECT_ROOT / outputs["smoke_audit"]
        payload = canonical_json_bytes(audit, newline=True)
        if args.check:
            if target.read_bytes() != payload:
                raise RuntimeError("Smoke audit does not reproduce byte-for-byte")
        else:
            target.write_bytes(payload)
        print(json.dumps({**audit, "live_calls_this_run": live_calls}, indent=2))
        return 0

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[f"task:{record['task_id']}"].append(record)
        grouped[f"bucket:{record['bucket']}"].append(record)
        if is_v3:
            grouped[f"answer_class:{record['answer_class']}"].append(record)
            for feature in record["feature_tags"]:
                grouped[f"feature:{feature}"].append(record)
    accuracy = {
        name: _rate(sum(item["strict_correct"] for item in items), len(items))
        for name, items in sorted(grouped.items())
    }
    overall = _rate(sum(item["strict_correct"] for item in records), len(records))
    semantic_overall = _rate(
        sum(item["semantic_equivalent_correct"] for item in records), len(records)
    )
    first_rate = _rate(
        sum(item["first_attempt_schema_compliant"] for item in records), len(records)
    )
    all_call_output_values = [
        int(item["output_tokens"])
        for item in services
        if item["output_tokens"] is not None
    ]
    all_call_reasoning_values = [
        int(item["reasoning_tokens"])
        for item in services
        if item["reasoning_tokens"] is not None
    ]
    all_call_latency_values = [
        int(item["latency_ms"])
        for item in services
        if item["latency_ms"] is not None
    ]
    max_output_utilization = round(
        max(all_call_output_values) / reasoner["max_output_tokens"], 8
    )
    utilization_limit = config["smoke"]["technical_gate"].get(
        "max_output_token_utilization_max"
    )
    gates = config["calibration"]["prospective_gates"]
    gate_results = {
        "parse_success": len(records) == frozen["cases"],
        "first_attempt_schema_compliance": first_rate >= gates["first_attempt_schema_compliance_min"],
        "overall_accuracy": overall >= gates["overall_accuracy_min"],
        "dag_answered_accuracy": accuracy["bucket:dag_answered"] >= gates["dag_answered_accuracy_min"],
        "cpdag_answered_accuracy": accuracy["bucket:cpdag_answered"] >= gates["cpdag_answered_accuracy_min"],
        "cpdag_undetermined_accuracy": accuracy["bucket:cpdag_undetermined"] >= gates["cpdag_undetermined_accuracy_min"],
        "per_task_accuracy": all(
            value >= gates["per_task_accuracy_min"]
            for name, value in accuracy.items()
            if name.startswith("task:")
        ),
    }
    record_payload = b"".join(canonical_json_bytes(item, newline=True) for item in records)
    audit = {
        "schema_version": (
            "fourgraph.t12_v3_openai_conformance_audit.v1"
            if is_v3
            else "fourgraph.t12_v2_openai_conformance_audit.v1"
        ),
        **common,
        "parse_success_rate": 1.0,
        "first_attempt_schema_compliance_rate": first_rate,
        "strict_overall_accuracy": overall,
        "semantic_equivalent_diagnostic_accuracy": semantic_overall,
        "strict_accuracy": accuracy,
        "engineering_diagnostics": {
            "captured_calls": len(services),
            "retry_calls": sum(
                max(0, int(item["attempts"]) - 1) for item in records
            ),
            "completed_calls": sum(
                item["response_status"] == "completed" for item in services
            ),
            "incomplete_calls": sum(
                item["response_status"] == "incomplete" for item in services
            ),
            "max_output_token_utilization": max_output_utilization,
            "max_output_token_utilization_gate": utilization_limit,
            "headroom_gate_passed": (
                utilization_limit is None
                or max_output_utilization <= utilization_limit
            ),
            "reasoning_tokens_distribution": {
                "min": min(all_call_reasoning_values),
                "median": _median(all_call_reasoning_values),
                "max": max(all_call_reasoning_values),
            },
            "latency_ms_distribution": {
                "min": min(all_call_latency_values),
                "median": _median(all_call_latency_values),
                "max": max(all_call_latency_values),
            },
        },
        "prospective_gates": gates,
        "gate_results": gate_results,
        "all_gates_passed": all(gate_results.values()),
        "causalds_oracle_development_eligible": all(gate_results.values()),
        "records_sha256": sha256_hex(record_payload),
    }
    audit_payload = canonical_json_bytes(audit, newline=True)
    records_path = PROJECT_ROOT / outputs["records"]
    audit_path = PROJECT_ROOT / outputs["audit"]
    if args.check:
        if records_path.read_bytes() != record_payload or audit_path.read_bytes() != audit_payload:
            raise RuntimeError("OpenAI candidate artifacts do not reproduce byte-for-byte")
    else:
        records_path.write_bytes(record_payload)
        audit_path.write_bytes(audit_payload)
    print(json.dumps({**audit, "live_calls_this_run": live_calls}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
