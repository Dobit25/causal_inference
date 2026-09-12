"""Run or replay the frozen T12 reasoner on primary development scenes."""

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

from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.causalds_scoring import load_official_target  # noqa: E402
from fourgraph.gemini_backend import GeminiReasonerBackend  # noqa: E402
from fourgraph.graph_contract import (  # noqa: E402
    GraphArtifact,
    canonical_json_bytes,
    sha256_hex,
)
from fourgraph.reasoner import (  # noqa: E402
    ReasonerPolicy,
    ReasonerReplayBackend,
    TASKS,
    conservative_target,
    load_reasoner_query,
    render_reasoner_prompt,
    run_fixed_reasoner,
    score_answer,
)


DEFAULT_CONFIG = Path("configs/t12_reasoner.yaml")


def _object(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if yaml_file else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _graph_manifest(path: Path) -> dict[str, GraphArtifact]:
    result: dict[str, GraphArtifact] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line:
            continue
        artifact = GraphArtifact.from_dict(json.loads(line))
        if artifact.scene_id in result:
            raise ValueError(f"Duplicate graph scene at {path}:{number}")
        result[artifact.scene_id] = artifact
    return result


def _append_raw(path: Path, call_id: str, attempts: tuple[Any, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        for attempt in attempts:
            stream.write(canonical_json_bytes(attempt.raw_log_record(call_id), newline=True))
        stream.flush()


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    payload = b"".join(canonical_json_bytes(item, newline=True) for item in records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class _ResumeBackend:
    """Replay captured attempts and use live API only for missing attempts."""

    def __init__(self, replay: Any, live: Any) -> None:
        self.replay = replay
        self.live = live
        self.live_keys: set[tuple[str, int]] = set()

    def complete(self, request: Any) -> Any:
        if self.replay is not None and self.replay.has_attempt(request.scene_id, request.attempt):
            return self.replay.complete(request)
        if self.live is None:
            raise RuntimeError(f"Missing replay response: {(request.scene_id, request.attempt)}")
        self.live_keys.add((request.scene_id, request.attempt))
        return self.live.complete(request)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--raw-log", type=Path)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--call-limit", type=int)
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = _object(config_path, yaml_file=True)
    config_sha = sha256_hex(config_path.read_bytes())
    source_root = args.source_root.resolve()
    split = _object(PROJECT_ROOT / config["source"]["split_manifest"])
    cohort = split["cohorts"][config["scope"]["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if len(dev_ids) != config["scope"]["expected_scenes"] or set(dev_ids) & holdout_ids:
        raise RuntimeError("Frozen T12 development split invariant failed")

    task_rows = [json.loads(line) for line in (PROJECT_ROOT / config["source"]["task_manifest"]).read_text(encoding="utf-8").splitlines() if line]
    dev_tasks = {(row["scene_id"], row["task_id"]) for row in task_rows if row["scene_id"] in dev_ids}
    expected_tasks = {(scene, task) for scene in dev_ids for task in TASKS}
    if dev_tasks != expected_tasks:
        raise RuntimeError("Frozen primary development task manifest changed")

    graph_sets: list[tuple[str, dict[str, GraphArtifact]]] = []
    graph_dev_ids = tuple(split["cohorts"]["graph"]["dev_ids"])
    for item in config["graphs"]:
        condition = item["condition"]
        if "manifest" in item:
            values = _graph_manifest(PROJECT_ROOT / item["manifest"])
        else:
            oracle_config = PROJECT_ROOT / "configs/t07_oracle_loader.yaml"
            oracle_sha = sha256_hex(oracle_config.read_bytes())
            values = {
                scene: load_causalds_oracle_graph(
                    source_root, scene, config_sha256=oracle_sha
                ).graph_artifact
                for scene in graph_dev_ids
            }
        if set(values) != set(graph_dev_ids):
            raise RuntimeError(f"{condition} graph manifest does not cover graph dev=8")
        graph_sets.append((condition, values))

    reasoner = config["reasoner"]
    policy = ReasonerPolicy(
        provider=reasoner["provider"],
        model_id=reasoner["model_id"],
        model_version=reasoner["model_version"],
        temperature=reasoner["temperature"],
        max_tokens=reasoner["max_tokens"],
        max_validation_retries=reasoner["max_validation_retries"],
    )
    template_path = PROJECT_ROOT / config["prompt"]["template"]
    template = template_path.read_text(encoding="utf-8")
    schema = _object(PROJECT_ROOT / config["prompt"]["response_schema"])
    raw_log = (args.raw_log or PROJECT_ROOT / config["outputs"]["raw_log_cache"] / f"{reasoner['model_version']}_dev.jsonl").resolve()
    replay = ReasonerReplayBackend.load(raw_log) if raw_log.exists() else None
    if args.check and replay is None:
        raise FileNotFoundError("--check requires the captured raw T12 log")
    if raw_log.exists() and not (args.resume or args.check):
        raise FileExistsError(f"Raw T12 log exists; use --resume or --check: {raw_log}")

    live_backend = None
    if not args.check:
        load_dotenv((PROJECT_ROOT / args.dotenv).resolve(), override=True)
        raw_keys = os.environ.get(reasoner["credential_env"], "")
        keys = [item.strip() for item in raw_keys.split(",") if item.strip()]
        live_backend = GeminiReasonerBackend(
            api_keys=keys,
            response_schema=schema,
            timeout_seconds=reasoner["timeout_seconds"],
        )
        if live_backend.sdk_version != reasoner["sdk_version"]:
            raise RuntimeError(
                f"google-genai SDK drift: expected={reasoner['sdk_version']}, actual={live_backend.sdk_version}"
            )

    records: list[dict[str, Any]] = []
    live_calls = 0
    processed = 0
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError("T12 attempted holdout access")
        for task_id in TASKS:
            query, variable_map, public_tasks_sha = load_reasoner_query(source_root, scene_id, task_id)
            official = load_official_target(source_root, query, variable_map)
            for condition, graphs in graph_sets:
                graph = graphs[scene_id]
                call_id = f"{scene_id}:{task_id}:{condition}"
                prompt = render_reasoner_prompt(graph, query, variable_map, template)
                for variable in variable_map.variables:
                    if variable.public_name in prompt:
                        raise RuntimeError(f"Public semantic name leaked into reasoner prompt: {scene_id}")
                use_replay = replay is not None and replay.has_call(call_id)
                if args.check and not use_replay:
                    raise RuntimeError(f"Missing replay call: {call_id}")
                backend = _ResumeBackend(replay, None if args.check else live_backend)
                result = run_fixed_reasoner(
                    graph_artifact=graph,
                    query=query,
                    variable_map=variable_map,
                    backend=backend,
                    policy=policy,
                    prompt_template=template,
                    call_id=call_id,
                )
                new_attempts = tuple(
                    item for item in result.attempts
                    if (call_id, item.attempt) in backend.live_keys
                )
                if new_attempts:
                    _append_raw(raw_log, call_id, new_attempts)
                    live_calls += len(new_attempts)
                if result.parsed is None:
                    raise RuntimeError(f"Reasoner failed after retries: {call_id}: {result.final_error}")
                uncertainty = conservative_target(graph.partial_graph, query)
                scores = score_answer(result.parsed, official, uncertainty)
                last = result.attempts[-1]
                records.append(
                    {
                        "schema_version": "fourgraph.t12_record.v1",
                        "scene_id": scene_id,
                        "task_id": task_id,
                        "graph_condition": condition,
                        "graph_type": graph.graph_type,
                        "graph_view": graph.graph_view,
                        "graph_sha256": graph.graph_sha256,
                        "graph_artifact_sha256": graph.artifact_sha256,
                        "variable_mapping_sha256": variable_map.mapping_sha256,
                        "query_sha256": query.sha256,
                        "public_tasks_sha256": public_tasks_sha,
                        "prompt_sha256": sha256_hex(last.prompt.encode("utf-8")),
                        "prompt_template_sha256": sha256_hex(template_path.read_bytes()),
                        "provider": last.response.provider,
                        "model_id": last.response.model_id,
                        "model_version": last.response.model_version,
                        "raw_response_sha256": last.response.raw_sha256,
                        "parsed_response": result.parsed.to_dict(),
                        "official_target": list(official.accepted),
                        "official_ground_truth_sha256": official.ground_truth_sha256,
                        "uncertainty_target": uncertainty.to_dict(),
                        **scores,
                        "latency_ms": last.response.latency_ms,
                        "input_tokens": last.response.input_tokens,
                        "output_tokens": last.response.output_tokens,
                        "retry_count": len(result.attempts) - 1,
                    }
                )
                processed += 1
                print(json.dumps({"call": processed, "call_id": call_id, "mode": "replay" if use_replay else "live", **scores}), flush=True)
                if args.call_limit is not None and processed >= args.call_limit:
                    print(json.dumps({"partial": True, "processed": processed, "live_calls": live_calls, "raw_log": str(raw_log)}, indent=2))
                    return 0

    output = PROJECT_ROOT / config["outputs"]["records"]
    payload = b"".join(canonical_json_bytes(item, newline=True) for item in records)
    if args.check:
        if output.read_bytes() != payload:
            raise RuntimeError("T12 records do not reproduce byte-for-byte")
    else:
        _write_jsonl(output, records)
    audit = {
        "schema_version": "fourgraph.t12_audit.v1",
        "t12_complete": True,
        "fixed_reasoner_contract_ready": True,
        "holdout_reasoner_ready": False,
        "holdout_blocker": "development Oracle-condition accuracy is 19/35; refine or replace reasoner before freeze",
        "development_scenes": len(dev_ids),
        "tasks_per_scene": len(TASKS),
        "graph_conditions": [item[0] for item in graph_sets],
        "records": len(records),
        "expected_records": len(dev_ids) * len(TASKS) * len(graph_sets),
        "oracle_answer_accuracy_mean": round(sum(item["oracle_answer_accuracy"] for item in records) / len(records), 8),
        "uncertainty_aware_correctness_mean": round(sum(item["uncertainty_aware_correctness"] for item in records) / len(records), 8),
        "undetermined_targets": sum(item["uncertainty_target"]["status"] == "undetermined" for item in records),
        "invalid_responses": 0,
        "calls_requiring_retry": sum(item["retry_count"] > 0 for item in records),
        "validation_retry_attempts": sum(item["retry_count"] for item in records),
        "holdout_accessed": False,
        "config_sha256": config_sha,
        "records_sha256": sha256_hex(payload),
        "raw_log_sha256": sha256_hex(raw_log.read_bytes()),
    }
    audit_path = PROJECT_ROOT / config["outputs"]["audit"]
    audit_payload = canonical_json_bytes(audit, newline=True)
    if args.check:
        if audit_path.read_bytes() != audit_payload:
            raise RuntimeError("T12 audit does not reproduce byte-for-byte")
    else:
        audit_path.write_bytes(audit_payload)
    print(json.dumps({**audit, "live_calls_this_run": live_calls}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
