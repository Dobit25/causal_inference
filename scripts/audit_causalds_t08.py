"""Audit T08 public inputs or replay pinned LLM graph responses."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.causalds_public import load_llm_graph_input  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.llm_backend import ReplayBackend  # noqa: E402
from fourgraph.llm_graph import (  # noqa: E402
    LLMGraphPolicy,
    build_llm_graph,
    expected_pairs,
    load_prompt_template,
    render_llm_graph_prompt,
)


DEFAULT_CONFIG = Path("configs/t08_llm_graph_builder.yaml")
DEFAULT_AUDIT = Path("data/manifests/t08_llm_graph_builder_audit.json")
DEFAULT_GRAPHS = Path("data/manifests/t08_dev_graphs.jsonl")


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _load_mapping(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    value = yaml.safe_load(text) if yaml_file else json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def _policy(config: dict[str, Any]) -> LLMGraphPolicy:
    llm = config["llm"]
    return LLMGraphPolicy(
        provider=llm["provider"],
        model_id=llm["model_id"],
        model_version=llm["model_version"],
        temperature=llm["temperature"],
        max_tokens=llm["max_tokens"],
        seed=llm["seed"],
        max_validation_retries=llm["max_validation_retries"],
    )


def build_outputs(
    source_root: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    replay_log: Path | None = None,
) -> tuple[bytes, bytes | None]:
    config = _load_mapping(config_path, yaml_file=True)
    scope = config["scope"]
    evidence_policy = config["evidence"]
    if scope["role"] != "dev" or scope["forbid_holdout_access"] is not True:
        raise ValueError("T08 audit is restricted to frozen development scenes")
    if evidence_policy["public_artifacts"] != ["story", "schema"]:
        raise ValueError("T08 public evidence must be exactly story and schema")
    if any(
        evidence_policy[key] is not False
        for key in (
            "allow_observational_table",
            "allow_tasks_or_queries",
            "allow_grading_or_oracle",
            "allow_gold_answers",
        )
    ):
        raise ValueError("T08 config permits forbidden evidence")

    split_path = PROJECT_ROOT / scope["split_manifest"]
    split = _load_mapping(split_path)
    cohort = split["cohorts"][scope["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if len(dev_ids) != scope["expected_scenes"] or set(dev_ids) & holdout_ids:
        raise ValueError("T08 frozen development scope is invalid")

    prompt_path = PROJECT_ROOT / config["prompt"]["template"]
    schema_path = PROJECT_ROOT / config["prompt"]["response_schema"]
    template, template_sha256 = load_prompt_template(prompt_path)
    if template_sha256 != config["prompt"]["template_sha256"]:
        raise RuntimeError("Frozen T08 prompt template hash mismatch")
    if file_sha256(schema_path) != config["prompt"]["response_schema_sha256"]:
        raise RuntimeError("Frozen T08 response schema hash mismatch")
    for relative_path, expected in config["freeze_anchors"].items():
        if file_sha256(PROJECT_ROOT / relative_path) != expected:
            raise RuntimeError(f"Frozen dependency changed: {relative_path}")

    config_sha256 = file_sha256(config_path)
    inputs = []
    loaded = {}
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError(f"T08 attempted holdout access: {scene_id}")
        evidence = load_llm_graph_input(
            source_root, scene_id, variant=config["source"]["variant"]
        )
        prompt = render_llm_graph_prompt(evidence, template)
        loaded[scene_id] = evidence
        inputs.append(
            {
                "scene_id": scene_id,
                "node_count": len(evidence.variable_map.node_ids),
                "pair_count": len(expected_pairs(evidence.variable_map.node_ids)),
                "story_sha256": evidence.story_sha256,
                "public_schema_sha256": evidence.public_schema_sha256,
                "variable_mapping_sha256": evidence.variable_map.mapping_sha256,
                "initial_prompt_sha256": sha256_hex(prompt.encode("utf-8")),
                "public_input_valid": True,
            }
        )

    live_configured = config["llm"]["live_backend_configured"] is True
    graph_bytes: bytes | None = None
    build_records: list[dict[str, Any]] = []
    successes = 0
    replay_sha256 = None
    if replay_log is not None:
        if not live_configured:
            raise ValueError("Replay requires a pinned live provider/model config")
        replay_sha256 = file_sha256(replay_log)
        backend = ReplayBackend.load(replay_log)
        if backend.scene_ids != frozenset(dev_ids):
            raise RuntimeError(
                "T08 replay log must contain exactly the frozen development scenes"
            )
        policy = _policy(config)
        artifacts = []
        for scene_id in dev_ids:
            result = build_llm_graph(
                loaded[scene_id],
                backend=backend,
                policy=policy,
                prompt_template=template,
                config_sha256=config_sha256,
            )
            build_records.append(result.manifest_record())
            if result.artifact is not None:
                successes += 1
                artifacts.append(result.artifact)
        if successes == len(dev_ids):
            graph_bytes = b"".join(artifact.to_json_bytes() for artifact in artifacts)

    complete = live_configured and replay_log is not None and successes == len(dev_ids)
    status = (
        "complete_llm_graph_builder_ready"
        if complete
        else "implementation_ready_live_backend_unset"
    )
    blocker = None
    if not complete:
        blocker = (
            "Exact provider, model_id, model_version, credential-backed adapter, "
            "and eight raw development responses are not configured."
        )
    audit = {
        "manifest_version": 1,
        "task": "T08",
        "status": status,
        "implementation": {
            "public_only_loader_ready": True,
            "prompt_renderer_ready": True,
            "strict_pair_parser_ready": True,
            "dag_validator_ready": True,
            "validation_retry_ready": True,
            "replay_backend_ready": True,
            "live_backend_configured": live_configured,
        },
        "scope": {
            "cohort": "graph_dev",
            "scene_ids": list(dev_ids),
            "scene_count": len(dev_ids),
            "holdout_scene_count": len(holdout_ids),
            "holdout_accessed": False,
            "tasks_or_queries_accessed": False,
            "observational_data_accessed": False,
            "grading_or_oracle_accessed": False,
            "downstream_reasoner_used": False,
        },
        "contract": {
            "graph_schema_version": "fourgraph.graph.v1",
            "response_schema_version": "fourgraph.llm_graph_response.v1",
            "config_sha256": config_sha256,
            "prompt_template_sha256": template_sha256,
            "response_schema_sha256": file_sha256(schema_path),
            "split_manifest_sha256": file_sha256(split_path),
            "pair_policy": "every_unordered_pair_exactly_once",
            "heuristic_graph_repair": False,
        },
        "model": {
            "provider": config["llm"]["provider"],
            "model_id": config["llm"]["model_id"],
            "model_version": config["llm"]["model_version"],
            "endpoint": config["llm"].get("endpoint"),
            "sdk": config["llm"].get("sdk"),
            "sdk_version": config["llm"].get("sdk_version"),
            "credential_env": config["llm"].get("credential_env"),
            "service_tier": config["llm"].get("service_tier"),
            "store": config["llm"].get("store"),
            "structured_outputs": config["llm"].get("structured_outputs"),
            "reasoning_effort": config["llm"].get("reasoning_effort"),
            "temperature": config["llm"]["temperature"],
            "max_tokens": config["llm"]["max_tokens"],
            "seed": config["llm"]["seed"],
            "max_validation_retries": config["llm"]["max_validation_retries"],
        },
        "public_input_audit": inputs,
        "development_build": {
            "replay_log_sha256": replay_sha256,
            "scenes_attempted": len(build_records),
            "scenes_succeeded": successes,
            "records": build_records,
            "dev_graphs_sha256": (
                sha256_hex(graph_bytes) if graph_bytes is not None else None
            ),
        },
        "verdict": {
            "implementation_ready": True,
            "llm_graph_builder_ready": complete,
            "blocker": blocker,
        },
    }
    return canonical_json_bytes(audit, newline=True), graph_bytes


def _check_bytes(path: Path, expected: bytes) -> None:
    if not path.is_file() or path.read_bytes() != expected:
        raise RuntimeError(f"Generated artifact is missing or stale: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--graph-output", type=Path, default=DEFAULT_GRAPHS)
    parser.add_argument("--replay-log", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit_bytes, graph_bytes = build_outputs(
        args.source_root, config_path=args.config, replay_log=args.replay_log
    )
    audit_path = PROJECT_ROOT / args.audit_output
    graph_path = PROJECT_ROOT / args.graph_output
    if args.check:
        _check_bytes(audit_path, audit_bytes)
        if graph_bytes is not None:
            _check_bytes(graph_path, graph_bytes)
    else:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_bytes(audit_bytes)
        if graph_bytes is not None:
            graph_path.parent.mkdir(parents=True, exist_ok=True)
            graph_path.write_bytes(graph_bytes)

    audit = json.loads(audit_bytes)
    print(
        json.dumps(
            {
                "mode": "check" if args.check else "write",
                "status": audit["status"],
                "public_inputs_valid": len(audit["public_input_audit"]),
                "dev_graphs_succeeded": audit["development_build"]["scenes_succeeded"],
                "holdout_accessed": audit["scope"]["holdout_accessed"],
                "llm_graph_builder_ready": audit["verdict"]["llm_graph_builder_ready"],
            },
            indent=2,
        )
    )
    return 0 if audit["verdict"]["implementation_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
