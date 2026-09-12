"""Audit or deterministically replay T10 Hybrid H1 development artifacts."""

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
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex, validate_hybrid_relationship  # noqa: E402
from fourgraph.hybrid_graph import HybridPolicy, build_hybrid_graph, load_graph_jsonl, load_prompt_template, render_hybrid_prompt, unresolved_pairs  # noqa: E402
from fourgraph.llm_backend import ReplayBackend  # noqa: E402


DEFAULT_CONFIG = Path("configs/t10_hybrid_graph_builder.yaml")


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _mapping(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if yaml_file else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def _policy(config: dict[str, Any]) -> HybridPolicy:
    llm = config["llm"]
    return HybridPolicy(llm["provider"], llm["model_id"], llm["model_version"], llm["temperature"], llm["max_tokens"], llm["seed"], llm["max_validation_retries"])


def _validate_policy(config: dict[str, Any]) -> None:
    evidence = config["evidence"]
    if evidence["public_artifacts"] != ["story", "schema"] or evidence["allowed"] != ["parent_graph", "public_story", "public_variable_semantics", "public_schema_types"]:
        raise ValueError("T10 evidence allowlist changed")
    forbidden = ("allow_observational_table", "allow_t08_llm_graph", "allow_t09_projected_dag", "allow_tasks_or_queries", "allow_grading_or_oracle", "allow_gold_answers")
    if any(evidence[key] is not False for key in forbidden):
        raise ValueError("T10 config permits forbidden evidence")
    if config["parent"]["projected_dag_forbidden"] is not True:
        raise ValueError("T10 projected-DAG access must remain forbidden")
    t08 = _mapping(PROJECT_ROOT / config["llm"]["source_freeze"], yaml_file=True)["llm"]
    keys = ("provider", "model_id", "model_version", "endpoint", "sdk", "sdk_version", "credential_env", "service_tier", "store", "structured_outputs", "reasoning_effort", "temperature", "max_tokens", "seed", "max_validation_retries", "transport_max_retries", "timeout_seconds")
    if any(config["llm"].get(key) != t08.get(key) for key in keys):
        raise RuntimeError("T10 model/config differs from the T08 semantic freeze")


def build_outputs(source_root: Path, *, config_path: Path = DEFAULT_CONFIG, replay_log: Path | None = None) -> tuple[bytes, bytes | None]:
    config = _mapping(config_path, yaml_file=True)
    _validate_policy(config)
    scope = config["scope"]
    split_path = PROJECT_ROOT / scope["split_manifest"]
    split = _mapping(split_path)
    cohort = split["cohorts"][scope["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if scope["role"] != "dev" or scope["forbid_holdout_access"] is not True or len(dev_ids) != scope["expected_scenes"] or set(dev_ids) & holdout_ids:
        raise ValueError("T10 frozen development scope is invalid")

    prompt_path = PROJECT_ROOT / config["prompt"]["template"]
    schema_path = PROJECT_ROOT / config["prompt"]["response_schema"]
    template, template_sha256 = load_prompt_template(prompt_path)
    if template_sha256 != config["prompt"]["template_sha256"] or file_sha256(schema_path) != config["prompt"]["response_schema_sha256"]:
        raise RuntimeError("Frozen T10 prompt/schema hash mismatch")
    for relative, expected in config["freeze_anchors"].items():
        if file_sha256(PROJECT_ROOT / relative) != expected:
            raise RuntimeError(f"Frozen dependency changed: {relative}")

    parent_path = PROJECT_ROOT / config["parent"]["raw_cpdag"]
    parents = load_graph_jsonl(parent_path)
    if set(parents) != set(dev_ids):
        raise RuntimeError("T09 raw CPDAG parent set changed")
    config_sha256 = file_sha256(config_path)
    inputs: dict[str, Any] = {}
    input_audit = []
    unresolved_total = 0
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError(f"T10 attempted holdout access: {scene_id}")
        evidence = load_llm_graph_input(source_root, scene_id, variant=config["source"]["variant"])
        parent = parents[scene_id]
        prompt = render_hybrid_prompt(evidence, parent, template)
        count = len(unresolved_pairs(parent))
        unresolved_total += count
        inputs[scene_id] = evidence
        input_audit.append({
            "scene_id": scene_id,
            "parent_artifact_sha256": parent.artifact_sha256,
            "parent_graph_sha256": parent.graph_sha256,
            "node_count": len(parent.nodes),
            "compelled_edge_count": len(parent.partial_graph.directed),
            "unresolved_edge_count": count,
            "story_sha256": evidence.story_sha256,
            "public_schema_sha256": evidence.public_schema_sha256,
            "variable_mapping_sha256": evidence.variable_map.mapping_sha256,
            "initial_prompt_sha256": sha256_hex(prompt.encode("utf-8")),
            "public_input_valid": True,
        })
    if unresolved_total != scope["expected_unresolved_edges"]:
        raise RuntimeError("Frozen unresolved edge total changed")

    graph_bytes: bytes | None = None
    records: list[dict[str, Any]] = []
    successes = retries = audited = 0
    replay_sha256 = None
    if replay_log is not None:
        replay_sha256 = file_sha256(replay_log)
        backend = ReplayBackend.load(replay_log)
        if backend.scene_ids != frozenset(dev_ids):
            raise RuntimeError("T10 replay log must contain exactly the frozen dev scenes")
        artifacts = []
        for scene_id in dev_ids:
            result = build_hybrid_graph(inputs[scene_id], parents[scene_id], backend=backend, policy=_policy(config), prompt_template=template, config_sha256=config_sha256)
            records.append(result.manifest_record())
            retries += result.retry_count
            if result.artifact is not None:
                validate_hybrid_relationship(parents[scene_id], result.artifact)
                successes += 1
                audited += len(result.artifact.edge_audit)
                artifacts.append(result.artifact)
        if successes == len(dev_ids):
            graph_bytes = b"".join(item.to_json_bytes() for item in artifacts)

    complete = replay_log is not None and successes == len(dev_ids) and audited == unresolved_total
    audit = {
        "manifest_version": 1,
        "task": "T10",
        "status": "complete_hybrid_h1_ready" if complete else "implementation_ready_pending_live_build",
        "implementation": {
            "parent_cpdag_loader_ready": True,
            "semantic_prompt_renderer_ready": True,
            "strict_orientation_parser_ready": True,
            "no_repair_validation_retry_ready": True,
            "t06_parent_child_validator_used": True,
            "replay_backend_ready": True,
        },
        "scope": {
            "cohort": "graph_dev",
            "scene_ids": list(dev_ids),
            "scene_count": len(dev_ids),
            "holdout_scene_count": len(holdout_ids),
            "holdout_accessed": False,
            "observational_data_accessed": False,
            "t08_llm_graph_accessed": False,
            "t09_projected_dag_accessed": False,
            "tasks_or_queries_accessed": False,
            "grading_or_oracle_accessed": False,
        },
        "contract": {
            "graph_schema_version": "fourgraph.graph.v1",
            "response_schema_version": "fourgraph.hybrid_orientation_response.v1",
            "config_sha256": config_sha256,
            "prompt_template_sha256": template_sha256,
            "response_schema_sha256": file_sha256(schema_path),
            "split_manifest_sha256": file_sha256(split_path),
            "parent_manifest_sha256": file_sha256(parent_path),
            "pair_policy": "every_unresolved_edge_exactly_once",
            "heuristic_graph_repair": False,
            "projected_dag_fallback": False,
        },
        "model": {key: config["llm"].get(key) for key in ("provider", "model_id", "model_version", "endpoint", "sdk", "sdk_version", "credential_env", "service_tier", "store", "structured_outputs", "reasoning_effort", "temperature", "max_tokens", "seed", "max_validation_retries")},
        "input_audit": input_audit,
        "development_build": {
            "replay_log_sha256": replay_sha256,
            "scenes_attempted": len(records),
            "scenes_succeeded": successes,
            "unresolved_edges_total": unresolved_total,
            "orientations_audited": audited,
            "validation_retries": retries,
            "skeleton_changes": 0 if complete else None,
            "compelled_direction_changes": 0 if complete else None,
            "equivalence_class_valid": successes,
            "parent_hash_valid": successes,
            "records": records,
            "dev_graphs_sha256": sha256_hex(graph_bytes) if graph_bytes is not None else None,
        },
        "verdict": {
            "t10_complete": complete,
            "hybrid_graph_builder_ready": complete,
            "blocker": None if complete else "Eight valid raw development responses have not yet been replayed.",
        },
    }
    return canonical_json_bytes(audit, newline=True), graph_bytes


def _check(path: Path, expected: bytes) -> None:
    if not path.is_file() or path.read_bytes() != expected:
        raise RuntimeError(f"Generated artifact is missing or stale: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--replay-log", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--graph-output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = _mapping(PROJECT_ROOT / args.config, yaml_file=True)
    audit_path = PROJECT_ROOT / (args.audit_output or Path(config["outputs"]["audit"]))
    graph_path = PROJECT_ROOT / (args.graph_output or Path(config["outputs"]["dev_graphs"]))
    audit_bytes, graph_bytes = build_outputs(args.source_root.resolve(), config_path=PROJECT_ROOT / args.config, replay_log=args.replay_log)
    if args.check:
        _check(audit_path, audit_bytes)
        if graph_bytes is not None:
            _check(graph_path, graph_bytes)
    else:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_bytes(audit_bytes)
        if graph_bytes is not None:
            graph_path.parent.mkdir(parents=True, exist_ok=True)
            graph_path.write_bytes(graph_bytes)
    audit = json.loads(audit_bytes)
    print(json.dumps({
        "mode": "check" if args.check else "write",
        "status": audit["status"],
        "scenes_succeeded": audit["development_build"]["scenes_succeeded"],
        "orientations_audited": audit["development_build"]["orientations_audited"],
        "holdout_accessed": audit["scope"]["holdout_accessed"],
        "t10_complete": audit["verdict"]["t10_complete"],
    }, indent=2))
    return 0 if audit["implementation"]["t06_parent_child_validator_used"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
