"""Offline T13 holdout pre-registration and integrity checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from fourgraph.graph_contract import canonical_json_bytes

TASKS = [
    "identification__one_valid_adjustment_set",
    "identification__all_minimal_adjustment_sets",
    "identification__minimal_adjustment_set_size",
    "identification__n_valid_adjustment_sets",
    "bias_diagnostic__forbidden_controls_list",
]
CONDITIONS = ["G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID", "G_ORACLE"]
FORBIDDEN_KEYS = {"gold_answer", "answer", "ground_truth", "oracle_edges", "edges"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _assert_safe_record(record: dict[str, Any]) -> None:
    forbidden = FORBIDDEN_KEYS.intersection(record)
    if forbidden:
        raise ValueError(f"T13 task record contains forbidden keys: {sorted(forbidden)}")


def _verify_declared_legacy_drift(root: Path, disclosure: dict[str, Any]) -> None:
    actual: dict[str, list[str]] = {}
    for task in ("T08", "T09", "T10", "T11"):
        config_name = {
            "T08": "configs/t08_llm_graph_builder.yaml",
            "T09": "configs/t09_scd_graph_builder.yaml",
            "T10": "configs/t10_hybrid_graph_builder.yaml",
            "T11": "configs/t11_graph_metrics.yaml",
        }[task]
        historical = yaml.safe_load((root / config_name).read_text(encoding="utf-8"))
        mismatches = [
            relative
            for relative, expected in historical["freeze_anchors"].items()
            if sha256_file(root / relative) != expected.upper()
        ]
        if mismatches:
            actual[task] = mismatches
    declared = disclosure["historical_source_anchor_drift"]
    if actual != declared:
        raise ValueError(f"Legacy anchor drift differs from T13 declaration: {actual}")


def _verify_protocol_matches_upstream(root: Path, protocol: dict[str, Any]) -> None:
    t05 = yaml.safe_load((root / "configs/t05_scd_frozen.yaml").read_text(encoding="utf-8"))
    t08 = yaml.safe_load((root / "configs/t08_llm_graph_builder.yaml").read_text(encoding="utf-8"))
    t10 = yaml.safe_load((root / "configs/t10_hybrid_graph_builder.yaml").read_text(encoding="utf-8"))
    t12 = yaml.safe_load((root / "configs/t12_v3_openai_mini_full_development.yaml").read_text(encoding="utf-8"))
    llm = protocol["llm_builder"]
    for key in ("model_snapshot", "endpoint", "reasoning_effort", "temperature", "max_output_tokens", "service_tier", "store", "max_validation_retries", "transport_max_retries", "timeout_seconds"):
        upstream_key = {"model_snapshot": "model_version", "max_output_tokens": "max_tokens"}.get(key, key)
        if llm[key] != t08["llm"][upstream_key]:
            raise ValueError(f"T13 LLM builder protocol drift: {key}")
    if llm["prompt"] != t08["prompt"]["version"] or llm["structured_outputs"] != t08["llm"]["structured_outputs"]:
        raise ValueError("T13 LLM builder prompt/output protocol drift")
    hybrid = protocol["hybrid"]
    if hybrid["prompt"] != t10["prompt"]["version"]:
        raise ValueError("T13 Hybrid prompt drift")
    for key in ("max_validation_retries", "transport_max_retries", "timeout_seconds"):
        if hybrid[key] != t10["llm"][key]:
            raise ValueError(f"T13 Hybrid runtime drift: {key}")
    scd = protocol["scd"]
    discovery = t05["discovery"]
    if (scd["algorithm"], scd["score"], scd["output"]) != (discovery["algorithm"], discovery["score"], discovery["output"]):
        raise ValueError("T13 SCD family drift")
    for key, value in discovery["parameters"].items():
        if scd[key] != value:
            raise ValueError(f"T13 SCD parameter drift: {key}")
    reasoner = protocol["reasoner"]
    for key in ("model_snapshot", "endpoint", "reasoning_effort", "max_output_tokens", "service_tier", "store", "structured_outputs", "max_validation_retries", "transport_max_retries", "timeout_seconds"):
        upstream_key = {"model_snapshot": "model_version"}.get(key, key)
        if reasoner[key] != t12["reasoner"][upstream_key]:
            raise ValueError(f"T13 reasoner protocol drift: {key}")
    if reasoner["temperature"] != t12["reasoner"]["sampling_temperature"]:
        raise ValueError("T13 reasoner temperature drift")
    if reasoner["graph_encoding"] != t12["graph_encoding"]["format"] or reasoner["node_labels"] != t12["graph_encoding"]["node_labels"]:
        raise ValueError("T13 reasoner graph encoding drift")


def _validate_manifest_schema(root: Path, manifest: dict[str, Any]) -> None:
    """Validate the closed top-level T13 schema without a new runtime dependency."""
    schema = json.loads((root / "schemas/t13_holdout_execution_v1.schema.json").read_text(encoding="utf-8"))
    missing = set(schema["required"]).difference(manifest)
    unknown = set(manifest).difference(schema["properties"])
    if missing or (schema.get("additionalProperties") is False and unknown):
        raise ValueError(f"T13 manifest schema mismatch: missing={sorted(missing)}, unknown={sorted(unknown)}")
    expected_version = schema["properties"]["schema_version"]["const"]
    if manifest["schema_version"] != expected_version:
        raise ValueError("T13 manifest schema-version mismatch")
    if len(manifest["graph_conditions"]) != 5 or len(set(manifest["graph_conditions"])) != 5:
        raise ValueError("T13 graph_conditions violates schema cardinality")


def build_t13(root: Path, config_path: Path) -> dict[str, bytes]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _verify_declared_legacy_drift(root, config["legacy_replay_disclosure"])
    _verify_protocol_matches_upstream(root, config["frozen_protocol"])
    scope = config["scope"]
    if config["graph_conditions"] != CONDITIONS:
        raise ValueError("T13 graph-condition order or membership drift")
    expected_scope = {
        "graph_holdout_scenes": 25,
        "primary_holdout_scenes": 20,
        "supplementary_holdout_scenes": 5,
        "tasks_per_primary_scene": 5,
        "supplementary_role": "exploratory_only",
    }
    for key, expected in expected_scope.items():
        if scope[key] != expected:
            raise ValueError(f"T13 declared scope drift: {key}")
    expected_execution = {
        "graph_scenes_per_condition": 25,
        "graph_metric_records": 125,
        "primary_query_records": 100,
        "primary_downstream_records": 500,
        "supplementary_inventory_records": 77,
        "supplementary_reasoner_records": 0,
    }
    for key, expected in expected_execution.items():
        if config["execution"][key] != expected:
            raise ValueError(f"T13 declared execution count drift: {key}")
    split_path = root / scope["split_manifest"]
    primary_source = root / scope["primary_task_manifest"]
    supplementary_source = root / scope["supplementary_task_manifest"]
    split = json.loads(split_path.read_text(encoding="utf-8"))

    graph_ids = split["cohorts"]["graph"]["holdout_ids"]
    primary_ids = split["cohorts"]["primary_downstream"]["holdout_ids"]
    supplementary_ids = split["cohorts"]["supplementary"]["holdout_ids"]
    if len(graph_ids) != 25 or len(primary_ids) != 20 or len(supplementary_ids) != 5:
        raise ValueError("T13 holdout cohort counts do not match 25/20/5")
    if set(primary_ids).intersection(supplementary_ids):
        raise ValueError("Primary and supplementary holdout cohorts overlap")
    if set(primary_ids).union(supplementary_ids) != set(graph_ids):
        raise ValueError("Nested holdout cohorts do not partition graph holdout")

    primary_all = load_jsonl(primary_source)
    primary = [row for row in primary_all if row["scene_id"] in primary_ids]
    supplementary_all = load_jsonl(supplementary_source)
    supplementary = [row for row in supplementary_all if row["scene_id"] in supplementary_ids]
    for row in primary + supplementary:
        _assert_safe_record(row)
    order_scene = {scene: index for index, scene in enumerate(graph_ids)}
    order_task = {task: index for index, task in enumerate(TASKS)}
    primary.sort(key=lambda row: (order_scene[row["scene_id"]], order_task[row["task_id"]]))
    supplementary.sort(key=lambda row: (order_scene[row["scene_id"]], row["task_id"]))
    if len(primary) != 100:
        raise ValueError(f"Expected 100 primary holdout tasks, found {len(primary)}")
    for scene in primary_ids:
        found = [row["task_id"] for row in primary if row["scene_id"] == scene]
        if found != TASKS:
            raise ValueError(f"Primary task panel mismatch for {scene}")
    if len(supplementary) != 77 or any(row["downstream_role"] != "exploratory_only" for row in supplementary):
        raise ValueError("Supplementary exploratory inventory mismatch")

    dependencies = []
    for relative in config["frozen_dependencies"]:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        dependencies.append({"path": relative, "sha256": sha256_file(path)})

    t12_audit = json.loads((root / "data/manifests/t12_v3_openai_mini_full_dev_audit.json").read_text(encoding="utf-8"))
    if not (t12_audit["full_development_matrix_passed"] and t12_audit["reasoner_frozen_for_holdout"] and t12_audit["t13_eligible"]):
        raise ValueError("T12 did not authorize T13")
    if t12_audit["holdout_accessed"]:
        raise ValueError("T12 reports holdout access")

    primary_bytes = b"".join(canonical_json_bytes(row, newline=True) for row in primary)
    supplementary_bytes = b"".join(canonical_json_bytes(row, newline=True) for row in supplementary)
    manifest = {
        "schema_version": "fourgraph.t13_holdout_execution.v1",
        "experiment_id": config["experiment_id"],
        "cohorts": {
            "graph": {"holdout_scene_ids": graph_ids, "count": 25},
            "primary_downstream": {"holdout_scene_ids": primary_ids, "count": 20, "tasks": TASKS, "tasks_per_scene": 5},
            "supplementary": {"holdout_scene_ids": supplementary_ids, "count": 5, "role": "exploratory_only", "pooled_with_primary": False, "frozen_inventory_records": 77, "scheduled_fixed_reasoner_records": 0},
        },
        "graph_conditions": CONDITIONS,
        "frozen_components": dependencies,
        "frozen_protocol": config["frozen_protocol"],
        "legacy_replay_disclosure": config["legacy_replay_disclosure"],
        "execution": {**config["execution"], "outputs": config["outputs"], "failure_policy": config["failure_policy"]},
        "metrics": {
            "graph": ["skeleton_precision_recall_f1", "skeleton_shd", "dag_directed_metrics", "dag_shd", "cpdag_state_metrics", "hybrid_orientation_attribution"],
            "downstream": ["oracle_answer_accuracy", "uncertainty_aware_correctness"],
            "sid_aid": "unavailable_not_zero",
        },
        "statistics": config["statistics"],
        "evidence_boundary": {"public_holdout_content_read": False, "gold_answers_read": False, "oracle_edges_read": False, "llm_calls": 0, "accuracy_computed": False},
        "lifecycle": {"status": "frozen_pre_holdout", "holdout_accessed": False, "t14_authorized": True, "t14_auto_start_allowed": False, "amendment_policy": "any_change_requires_new_experiment_version"},
    }
    _validate_manifest_schema(root, manifest)
    manifest_bytes = canonical_json_bytes(manifest, newline=True)
    audit = {
        "schema_version": "fourgraph.t13_holdout_execution_audit.v1",
        "config_sha256": sha256_file(config_path),
        "schema_sha256": sha256_file(root / "schemas/t13_holdout_execution_v1.schema.json"),
        "primary_tasks_sha256": hashlib.sha256(primary_bytes).hexdigest().upper(),
        "supplementary_tasks_sha256": hashlib.sha256(supplementary_bytes).hexdigest().upper(),
        "execution_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest().upper(),
        "dependency_count": len(dependencies),
        "schema_validation": "builtin_closed_top_level_contract_passed",
        "cohort_checks": {"graph_25": True, "primary_20": True, "supplementary_5": True, "nested_partition": True, "one_role_per_scene": True, "primary_5_tasks_each": True},
        "expected_counts": {"graph_artifacts_non_oracle": 100, "oracle_graphs_in_memory": 25, "graph_metric_records": 125, "primary_downstream_records": 500, "supplementary_inventory_records": 77, "supplementary_reasoner_records": 0},
        "scope": {"api_calls": 0, "frozen_metadata_manifests_read": [scope["split_manifest"], scope["primary_task_manifest"], scope["supplementary_task_manifest"]], "holdout_content_artifacts_read": [], "gold_answers_read": False, "oracle_edges_read": False, "accuracy_results_created": False, "holdout_accessed": False},
        "upstream_gate": {"full_development_matrix_passed": True, "reasoner_frozen_for_holdout": True, "t13_eligible": True},
        "legacy_replay": {"historical_artifacts_unchanged": True, "declared_source_anchor_drift_present": True, "current_t14_implementation_hash_pinned": True},
        "verdict": {"t13_complete": True, "configuration_frozen": True, "t14_authorized": True, "t14_started": False},
    }
    return {
        config["outputs"]["primary_tasks"]: primary_bytes,
        config["outputs"]["supplementary_tasks"]: supplementary_bytes,
        config["outputs"]["execution_manifest"]: manifest_bytes,
        config["outputs"]["audit"]: canonical_json_bytes(audit, newline=True),
    }
