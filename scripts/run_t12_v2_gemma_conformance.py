"""Run the frozen Gemma candidate on the answer-free T12 v2 conformance suite."""

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

from fourgraph.gemini_backend import GeminiReasonerBackend  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.llm_backend import LLMCallRequest  # noqa: E402
from fourgraph.reasoner import ReasonerQuery, _canonical_answer  # noqa: E402
from fourgraph.reasoner_v2 import (  # noqa: E402
    CanonicalResponseCache,
    build_cache_identity,
    parse_task_specific_response,
)


DEFAULT_CONFIG = Path("configs/t12_v2_design.yaml")


def _object(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    value = (
        yaml.safe_load(path.read_text(encoding="utf-8"))
        if yaml_file
        else json.loads(path.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _render(template: str, row: dict[str, Any]) -> str:
    replacements = {
        "{{GRAPH_JSON}}": canonical_json_bytes(row["graph"]).decode("utf-8"),
        "{{QUERY_JSON}}": canonical_json_bytes(row["query"]).decode("utf-8"),
        "{{GLOSSARY_JSON}}": canonical_json_bytes(row["glossary"]).decode("utf-8"),
    }
    prompt = template
    for marker, value in replacements.items():
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


def _correct(parsed: Any, row: dict[str, Any]) -> bool:
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


def _gemini_schema(value: Any) -> Any:
    """Remove regex constraints that Gemma's nested constrained decoder loops on."""

    if isinstance(value, dict):
        transformed = {
            key: _gemini_schema(item)
            for key, item in value.items()
            if key not in {"$schema", "pattern"}
        }
        properties = transformed.get("properties")
        if isinstance(properties, dict) and "adjustment_sets" in properties:
            contract = properties["adjustment_sets"]
            if isinstance(contract, dict) and isinstance(contract.get("oneOf"), list):
                contract["oneOf"][0] = {"type": "array"}
        return transformed
    if isinstance(value, list):
        return [_gemini_schema(item) for item in value]
    return value


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 8) if denominator else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--call-limit", type=int)
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = _object(config_path, yaml_file=True)
    reasoner = config["reasoner"]
    calibration = config["calibration"]
    outputs = config["outputs"]
    suite_path = PROJECT_ROOT / calibration["suite"]
    rows = [
        json.loads(line)
        for line in suite_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if len(rows) != calibration["cases"] or any(
        row["uses_causalds_story"] or row["uses_causalds_answer"] for row in rows
    ):
        raise RuntimeError("Synthetic-suite evidence invariant failed")

    template_path = PROJECT_ROOT / reasoner["prompt"]
    template = template_path.read_text(encoding="utf-8")
    raw_path = PROJECT_ROOT / outputs["raw_log"]
    cache_path = PROJECT_ROOT / outputs["cache"]
    records_path = PROJECT_ROOT / outputs["records"]
    audit_path = PROJECT_ROOT / outputs["audit"]
    if (raw_path.exists() or cache_path.exists()) and not (args.resume or args.check):
        raise FileExistsError("Existing v2 run found; use --resume or --check")
    cache = CanonicalResponseCache.load(cache_path)
    raw_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if raw_path.exists():
        for line in raw_path.read_text(encoding="utf-8").splitlines():
            if line:
                item = json.loads(line)
                if item.get("cache_key"):
                    raw_history[item["cache_key"]].append(item)

    decoding_base = {
        "temperature": reasoner["temperature"],
        "max_tokens": reasoner["max_tokens"],
        "max_validation_retries": reasoner["max_validation_retries"],
        "response_contract": reasoner["response_contract"],
        "provider_schema_transform": reasoner["provider_schema_transform"],
    }
    backends: dict[str, GeminiReasonerBackend] = {}
    if not args.check:
        load_dotenv((PROJECT_ROOT / args.dotenv).resolve(), override=True)
        keys = [
            item.strip()
            for item in os.environ.get(reasoner["credential_env"], "").split(",")
            if item.strip()
        ]
        for schema_rel in sorted({row["response_schema"] for row in rows}):
            backend = GeminiReasonerBackend(
                api_keys=keys,
                response_schema=_gemini_schema(_object(PROJECT_ROOT / schema_rel)),
                timeout_seconds=reasoner["timeout_seconds"],
            )
            if backend.sdk_version != reasoner["sdk_version"]:
                raise RuntimeError("google-genai SDK version drift")
            backends[schema_rel] = backend

    records: list[dict[str, Any]] = []
    live_calls = 0
    cache_hits = 0
    for index, row in enumerate(rows, 1):
        query = _query(row)
        prompt = _render(template, row)
        schema_path = PROJECT_ROOT / row["response_schema"]
        decoding = {
            **decoding_base,
            "response_schema_sha256": sha256_hex(schema_path.read_bytes()),
            "provider_response_schema_sha256": sha256_hex(
                canonical_json_bytes(_gemini_schema(_object(schema_path)))
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
        attempts = 0
        first_attempt_valid = False
        if raw_text is not None:
            cache_hits += 1
            parsed = parse_task_specific_response(raw_text, query)
            history = raw_history.get(identity.cache_key, [])
            if not history:
                raise RuntimeError(f"Cached response has no auditable raw call: {row['case_id']}")
            attempts = len(history)
            first_attempt_valid = history[0]["validation_error"] is None
        elif args.check:
            raise RuntimeError(f"Missing cached response in --check: {row['case_id']}")
        else:
            parsed = None
            validation_error = None
            for attempt in range(reasoner["max_validation_retries"] + 1):
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
                    temperature=reasoner["temperature"],
                    max_tokens=reasoner["max_tokens"],
                    seed=None,
                )
                response = backends[row["response_schema"]].complete(request)
                live_calls += 1
                attempts = attempt + 1
                try:
                    parsed = parse_task_specific_response(response.raw_text, query)
                    validation_error = None
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    validation_error = str(exc)
                raw_record = {
                        "schema_version": "fourgraph.t12_v2_raw_call.v1",
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
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "latency_ms": response.latency_ms,
                        "sdk_version": response.sdk_version,
                        "provider_response_json": response.provider_response_json,
                        "validation_error": validation_error,
                    }
                _append_raw(raw_path, raw_record)
                raw_history[identity.cache_key].append(raw_record)
                if parsed is not None:
                    first_attempt_valid = attempt == 0
                    raw_text = response.raw_text
                    cache.put(identity, raw_text)
                    cache.write(cache_path)
                    break
            if parsed is None or raw_text is None:
                raise RuntimeError(f"Gemma failed response validation: {row['case_id']}")

        records.append(
            {
                "schema_version": "fourgraph.t12_v2_conformance_score.v1",
                "case_id": row["case_id"],
                "task_id": row["task_id"],
                "bucket": row["bucket"],
                "feature_tags": row["feature_tags"],
                "cache_key": identity.cache_key,
                "prompt_sha256": sha256_hex(prompt.encode("utf-8")),
                "raw_response_sha256": sha256_hex(raw_text.encode("utf-8")),
                "parsed_response": parsed.to_dict(),
                "expected": row["expected"],
                "correct": _correct(parsed, row),
                "first_attempt_schema_compliant": first_attempt_valid,
                "attempts": attempts,
            }
        )
        print(
            json.dumps(
                {
                    "case": index,
                    "case_id": row["case_id"],
                    "mode": "cache" if attempts == 0 else "live",
                    "correct": records[-1]["correct"],
                }
            ),
            flush=True,
        )
        if args.call_limit is not None and live_calls >= args.call_limit:
            print(json.dumps({"partial": True, "live_calls": live_calls}))
            return 0

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[f"task:{record['task_id']}"].append(record)
        grouped[f"bucket:{record['bucket']}"] .append(record)
    accuracy = {
        name: _rate(sum(item["correct"] for item in items), len(items))
        for name, items in sorted(grouped.items())
    }
    overall = _rate(sum(item["correct"] for item in records), len(records))
    parse_rate = 1.0
    first_rate = _rate(
        sum(item["first_attempt_schema_compliant"] for item in records), len(records)
    )
    gates = calibration["prospective_gates"]
    gate_results = {
        "parse_success": parse_rate >= gates["parse_success_rate_min"],
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
    payload = b"".join(canonical_json_bytes(item, newline=True) for item in records)
    audit = {
        "schema_version": "fourgraph.t12_v2_conformance_audit.v1",
        "provider": reasoner["provider"],
        "model_id": reasoner["model_id"],
        "model_version": reasoner["model_version"],
        "cases": len(records),
        "parse_success_rate": parse_rate,
        "first_attempt_schema_compliance_rate": first_rate,
        "overall_accuracy": overall,
        "accuracy": accuracy,
        "prospective_gates": gates,
        "gate_results": gate_results,
        "all_gates_passed": all(gate_results.values()),
        "causalds_oracle_development_eligible": all(gate_results.values()),
        "holdout_accessed": False,
        "config_sha256": sha256_hex(config_path.read_bytes()),
        "suite_sha256": sha256_hex(suite_path.read_bytes()),
        "records_sha256": sha256_hex(payload),
        "raw_log_sha256": sha256_hex(raw_path.read_bytes()),
        "cache_sha256": sha256_hex(cache_path.read_bytes()),
    }
    audit_payload = canonical_json_bytes(audit, newline=True)
    if args.check:
        if records_path.read_bytes() != payload or audit_path.read_bytes() != audit_payload:
            raise RuntimeError("T12 v2 Gemma artifacts do not reproduce byte-for-byte")
    else:
        records_path.parent.mkdir(parents=True, exist_ok=True)
        records_path.write_bytes(payload)
        audit_path.write_bytes(audit_payload)
    print(json.dumps({**audit, "live_calls_this_run": live_calls, "cache_hits": cache_hits}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
