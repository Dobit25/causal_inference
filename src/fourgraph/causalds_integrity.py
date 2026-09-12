"""T04 parquet, mapping, graph, task, and access-boundary integrity audit."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from fourgraph.causalds_access import (
    GradingPurpose,
    resolve_grading_artifact,
    resolve_public_artifact,
    resolve_public_story,
)
from fourgraph.causalds_inventory import PRIMARY_TASK_IDS, is_dag, load_json


FORBIDDEN_PUBLIC_KEYS = {
    "answer_key",
    "gold",
    "gold_answer",
    "grading",
    "ground_truth",
    "target_answer",
}

TASK_VARIABLE_KEYS = {
    "available_vars",
    "columns",
    "conditioning_var",
    "observed_vars",
}


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def serialize_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def serialize_jsonl(records: Sequence[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(record) for record in records)


def _forbidden_keys(value: Any, prefix: str = "") -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_PUBLIC_KEYS:
                found.append(path)
            found.extend(_forbidden_keys(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_forbidden_keys(nested, f"{prefix}[{index}]"))
    return found


def _normal_dtype(data_type: pa.DataType) -> str:
    if pa.types.is_float64(data_type):
        return "float64"
    if pa.types.is_float32(data_type):
        return "float32"
    if pa.types.is_int64(data_type):
        return "int64"
    if pa.types.is_int32(data_type):
        return "int32"
    if pa.types.is_boolean(data_type):
        return "bool"
    if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
        return "string"
    return str(data_type)


def _count_true(mask: pa.Array) -> int:
    value = pc.sum(pc.cast(pc.fill_null(mask, False), pa.int64())).as_py()
    return int(value or 0)


def _safe_number(value: Any) -> int | float | str | None:
    if value is None or isinstance(value, (str, int)):
        return value
    numeric = float(value)
    if math.isfinite(numeric):
        return numeric
    return str(numeric)


def _column_stats(
    array: pa.ChunkedArray,
    expected: dict[str, Any],
) -> dict[str, Any]:
    combined = array.combine_chunks()
    floating = pa.types.is_floating(combined.type)
    null_count = int(combined.null_count)
    nan_count = _count_true(pc.is_nan(combined)) if floating else 0
    inf_count = _count_true(pc.is_inf(combined)) if floating else 0
    distinct_values = pc.unique(combined).to_pylist()
    distinct_non_null = [
        value
        for value in distinct_values
        if value is not None
        and not (isinstance(value, float) and math.isnan(value))
    ]
    distinct_non_null.sort(key=lambda value: (str(type(value)), repr(value)))
    min_max = pc.min_max(combined).as_py()
    expected_binary = bool(expected.get("is_binary"))
    expected_support = expected.get("values")
    actual_support = [_safe_number(value) for value in distinct_non_null]
    binary_support_matches = True
    if expected_binary:
        binary_support_matches = actual_support == [
            _safe_number(value) for value in sorted(expected_support or [])
        ]

    return {
        "actual_dtype": _normal_dtype(combined.type),
        "expected_dtype": str(expected.get("dtype")),
        "dtype_matches": _normal_dtype(combined.type) == expected.get("dtype"),
        "null_count": null_count,
        "nan_count": nan_count,
        "infinite_count": inf_count,
        "distinct_non_null_count": len(distinct_non_null),
        "constant": len(distinct_non_null) <= 1,
        "minimum": _safe_number(min_max.get("min")),
        "maximum": _safe_number(min_max.get("max")),
        "expected_binary": expected_binary,
        "actual_support": actual_support if expected_binary else None,
        "binary_support_matches": binary_support_matches,
    }


def audit_parquet(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    """Inspect actual parquet values and compare them with released schema metadata."""
    parquet_file = pq.ParquetFile(path)
    table = parquet_file.read()
    expected_columns = list(expected.get("columns", {}))
    actual_columns = table.column_names
    duplicate_column_names = len(actual_columns) != len(set(actual_columns))
    column_stats = {
        name: _column_stats(table[name], expected["columns"].get(name, {}))
        for name in actual_columns
        if name in expected.get("columns", {})
    }

    row_values = zip(*(table[name].to_pylist() for name in actual_columns))
    unique_row_count = len(set(row_values))
    duplicate_row_count = table.num_rows - unique_row_count
    all_columns_healthy = all(
        stats["dtype_matches"]
        and stats["null_count"] == 0
        and stats["nan_count"] == 0
        and stats["infinite_count"] == 0
        and not stats["constant"]
        and stats["binary_support_matches"]
        for stats in column_stats.values()
    )

    checks = {
        "readable": True,
        "row_count_matches": table.num_rows == int(expected.get("n_rows", -1)),
        "column_count_matches": table.num_columns
        == int(expected.get("n_columns", -1)),
        "column_order_matches": actual_columns == expected_columns,
        "column_names_unique": not duplicate_column_names,
        "all_expected_columns_audited": set(column_stats) == set(expected_columns),
        "all_columns_healthy": all_columns_healthy,
    }
    return {
        "path_name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_count": table.num_rows,
        "column_count": table.num_columns,
        "column_names": actual_columns,
        "row_group_count": parquet_file.metadata.num_row_groups,
        "unique_row_count": unique_row_count,
        "duplicate_row_count": duplicate_row_count,
        "duplicate_row_fraction": round(
            duplicate_row_count / table.num_rows if table.num_rows else 0.0, 8
        ),
        "columns": column_stats,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _task_variable_references(task: dict[str, Any]) -> list[str]:
    references: list[str] = []
    inputs = task.get("inputs", {})
    if not isinstance(inputs, dict):
        return references
    for key in TASK_VARIABLE_KEYS:
        value = inputs.get(key)
        if isinstance(value, str):
            references.append(value)
        elif isinstance(value, list):
            references.extend(str(item) for item in value)
    return sorted(set(references))


def _task_manifest_record(
    scene_id: str,
    task: dict[str, Any],
    *,
    cohort: str,
) -> dict[str, Any]:
    response_schema = task.get("response_schema")
    prompt = str(task.get("prompt", ""))
    return {
        "scene_id": scene_id,
        "task_id": str(task["task_id"]),
        "cohort": cohort,
        "downstream_role": (
            "primary" if cohort == "primary_downstream" else "exploratory_only"
        ),
        "task_type": task.get("task_type"),
        "rung": task.get("rung"),
        "output_type": task.get("output_type"),
        "output_variant": task.get("output_variant"),
        "input_mode": task.get("input_mode"),
        "is_symbolic": bool(task.get("is_symbolic")),
        "scoring_key": task.get("scoring_key"),
        "input_variable_references": _task_variable_references(task),
        "public_prompt_sha256": sha256(prompt.encode("utf-8")).hexdigest(),
        "response_schema_sha256": (
            sha256(_canonical_json_bytes(response_schema)).hexdigest()
            if response_schema is not None
            else None
        ),
    }


def _scene_audit(
    source_root: Path,
    scene_id: str,
    cohort: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    variant = "clean"
    data_path = resolve_public_artifact(
        source_root, scene_id, variant, "data"
    )
    schema_path = resolve_public_artifact(
        source_root, scene_id, variant, "schema"
    )
    tasks_path = resolve_public_artifact(
        source_root, scene_id, variant, "tasks"
    )
    test_features_path = resolve_public_artifact(
        source_root, scene_id, variant, "test_features"
    )
    story_path = resolve_public_story(source_root, scene_id)
    ground_truth_path = resolve_grading_artifact(
        source_root,
        scene_id,
        "ground_truth",
        purpose=GradingPurpose.INTEGRITY_AUDIT,
    )
    grading_test_path = resolve_grading_artifact(
        source_root,
        scene_id,
        "test",
        purpose=GradingPurpose.INTEGRITY_AUDIT,
    )

    schema = load_json(schema_path)
    task_document = load_json(tasks_path)
    ground_truth = load_json(ground_truth_path)
    tasks = task_document.get("tasks", [])
    task_ids = [str(task["task_id"]) for task in tasks]
    tasks_by_id = {str(task["task_id"]): task for task in tasks}
    graph = ground_truth["graph"]
    metadata = ground_truth.get("metadata", {})
    mechanisms = metadata.get("data_mechanisms", {})
    per_node = mechanisms.get("per_node", {})
    mapping = ground_truth.get("mapping", {})
    nodes = [str(node) for node in graph.get("nodes", [])]
    edges = graph.get("edges", [])
    observed_nodes = [str(node) for node in graph.get("observed_nodes", [])]
    latent_nodes = [str(node) for node in graph.get("latent_nodes", [])]
    observed_names = {mapping[node] for node in observed_nodes if node in mapping}
    data_columns = set(schema.get("columns", {}))

    data_audit = audit_parquet(
        data_path, schema["datasets"]["data.parquet"]
    )
    test_features_audit = audit_parquet(
        test_features_path, schema["datasets"]["test_features.parquet"]
    )

    conceptual_type_matches = True
    for node in observed_nodes:
        name = mapping.get(node)
        expected_binary = per_node.get(node, {}).get("var_type") == "binary"
        schema_binary = bool(schema.get("columns", {}).get(name, {}).get("is_binary"))
        if expected_binary != schema_binary:
            conceptual_type_matches = False

    variable_references = {
        str(task["task_id"]): _task_variable_references(task) for task in tasks
    }
    task_variable_references_valid = all(
        set(references) <= data_columns
        for references in variable_references.values()
    )
    treatment_name = str(graph.get("treatment_named", ""))
    outcome_name = str(graph.get("outcome_named", ""))
    primary_prompt_query_matches = True
    if cohort == "primary_downstream":
        primary_prompt_query_matches = all(
            treatment_name in str(tasks_by_id[task_id].get("prompt", ""))
            and outcome_name in str(tasks_by_id[task_id].get("prompt", ""))
            for task_id in PRIMARY_TASK_IDS
            if task_id in tasks_by_id
        )

    public_forbidden_keys = sorted(
        set(_forbidden_keys(schema) + _forbidden_keys(task_document))
    )
    primary_panel_exact = all(Counter(task_ids)[task_id] == 1 for task_id in PRIMARY_TASK_IDS)
    if cohort != "primary_downstream":
        primary_panel_exact = True
    selected_tasks = (
        [tasks_by_id[task_id] for task_id in PRIMARY_TASK_IDS]
        if cohort == "primary_downstream"
        else sorted(tasks, key=lambda task: str(task["task_id"]))
    )
    manifest_records = [
        _task_manifest_record(scene_id, task, cohort=cohort)
        for task in selected_tasks
    ]

    checks = {
        "all_required_files_present": all(
            path.is_file()
            for path in (
                data_path,
                schema_path,
                tasks_path,
                test_features_path,
                story_path,
                ground_truth_path,
                grading_test_path,
            )
        ),
        "data_parquet_passed": data_audit["passed"],
        "test_features_parquet_passed": test_features_audit["passed"],
        "scene_ids_match": task_document.get("scene_id") == scene_id
        and ground_truth.get("scene_id") == scene_id,
        "observation_variant_clean": task_document.get("observation_variant")
        == "clean",
        "task_ids_unique": len(task_ids) == len(set(task_ids)),
        "primary_task_panel_exact": primary_panel_exact,
        "primary_response_schemas_present": all(
            tasks_by_id[task_id].get("response_schema") is not None
            for task_id in PRIMARY_TASK_IDS
            if cohort == "primary_downstream"
        ),
        "task_variable_references_valid": task_variable_references_valid,
        "primary_prompt_query_matches": primary_prompt_query_matches,
        "graph_is_dag": is_dag(nodes, edges),
        "graph_edges_unique": len({tuple(edge) for edge in edges}) == len(edges),
        "node_mapping_complete": set(mapping) == set(nodes),
        "observed_mapping_matches_data_columns": observed_names == data_columns,
        "no_latent_nodes": not latent_nodes,
        "observed_nodes_cover_graph": set(observed_nodes) == set(nodes),
        "conceptual_types_match_schema_binary_flags": conceptual_type_matches,
        "mechanism_metadata_complete": set(per_node) == set(nodes),
        "public_documents_exclude_grading_keys": not public_forbidden_keys,
    }
    return {
        "scene_id": scene_id,
        "cohort": cohort,
        "passed": all(checks.values()),
        "checks": checks,
        "public_data": data_audit,
        "public_test_features": test_features_audit,
        "graph_summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "observed_node_count": len(observed_nodes),
            "latent_node_count": len(latent_nodes),
            "structural_label": metadata.get("structural_label"),
        },
        "task_summary": {
            "task_count": len(tasks),
            "primary_task_count": sum(
                task_id in set(PRIMARY_TASK_IDS) for task_id in task_ids
            ),
            "variable_references": variable_references,
        },
        "public_forbidden_keys": public_forbidden_keys,
        "file_hashes": {
            "story_md": sha256_file(story_path),
            "schema_json": sha256_file(schema_path),
            "tasks_json": sha256_file(tasks_path),
            "ground_truth_json_grading_only": sha256_file(ground_truth_path),
            "test_parquet_grading_only": sha256_file(grading_test_path),
        },
    }, manifest_records


def _aggregate_scene_results(scene_results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    data_duplicate_rates = [
        scene["public_data"]["duplicate_row_fraction"] for scene in scene_results
    ]
    public_columns = [
        column
        for scene in scene_results
        for column in scene["public_data"]["columns"].values()
    ]
    return {
        "scene_count": len(scene_results),
        "passed_scenes": sum(scene["passed"] for scene in scene_results),
        "failed_scene_ids": sorted(
            scene["scene_id"] for scene in scene_results if not scene["passed"]
        ),
        "data_rows_total": sum(
            scene["public_data"]["row_count"] for scene in scene_results
        ),
        "data_columns_total": len(public_columns),
        "null_values_total": sum(column["null_count"] for column in public_columns),
        "nan_values_total": sum(column["nan_count"] for column in public_columns),
        "infinite_values_total": sum(
            column["infinite_count"] for column in public_columns
        ),
        "constant_columns_total": sum(column["constant"] for column in public_columns),
        "binary_support_mismatches": sum(
            column["expected_binary"] and not column["binary_support_matches"]
            for column in public_columns
        ),
        "duplicate_row_fraction_range": [
            round(min(data_duplicate_rates), 8),
            round(max(data_duplicate_rates), 8),
        ],
        "actual_dtype_counts": dict(
            sorted(Counter(column["actual_dtype"] for column in public_columns).items())
        ),
    }


def build_t04_artifacts(
    source_root: Path,
    source_manifest: dict[str, Any],
    provisional_split: dict[str, Any],
) -> dict[str, bytes | None]:
    """Audit 33 scenes and build task/integrity/frozen-split artifacts."""
    graph = provisional_split["cohorts"]["graph"]
    primary_ids = set(
        provisional_split["cohorts"]["primary_downstream"]["dev_ids"]
        + provisional_split["cohorts"]["primary_downstream"]["holdout_ids"]
    )
    supplementary_ids = set(
        provisional_split["cohorts"]["supplementary"]["dev_ids"]
        + provisional_split["cohorts"]["supplementary"]["holdout_ids"]
    )
    graph_ids = sorted(graph["dev_ids"] + graph["holdout_ids"])
    if primary_ids | supplementary_ids != set(graph_ids) or primary_ids & supplementary_ids:
        raise ValueError("Provisional split does not satisfy nested partition")

    scene_results = []
    primary_records = []
    supplementary_records = []
    for scene_id in graph_ids:
        cohort = (
            "primary_downstream" if scene_id in primary_ids else "supplementary"
        )
        result, records = _scene_audit(source_root.resolve(), scene_id, cohort)
        scene_results.append(result)
        if cohort == "primary_downstream":
            primary_records.extend(records)
        else:
            supplementary_records.extend(records)

    primary_records.sort(
        key=lambda row: (
            row["scene_id"],
            PRIMARY_TASK_IDS.index(row["task_id"]),
        )
    )
    supplementary_records.sort(key=lambda row: (row["scene_id"], row["task_id"]))
    primary_bytes = serialize_jsonl(primary_records)
    supplementary_bytes = serialize_jsonl(supplementary_records)
    aggregate = _aggregate_scene_results(scene_results)
    all_scenes_pass = aggregate["passed_scenes"] == 33
    task_gates = {
        "primary_record_count_is_135": len(primary_records) == 135,
        "primary_has_27_scenes": len(
            {record["scene_id"] for record in primary_records}
        )
        == 27,
        "primary_each_scene_has_five_tasks": all(
            sum(record["scene_id"] == scene_id for record in primary_records) == 5
            for scene_id in primary_ids
        ),
        "supplementary_has_six_scenes": len(
            {record["scene_id"] for record in supplementary_records}
        )
        == 6,
        "task_manifests_exclude_gold_fields": not _forbidden_keys(primary_records)
        and not _forbidden_keys(supplementary_records),
    }
    nesting_gates = {
        "graph_count_is_33": len(graph_ids) == 33,
        "primary_count_is_27": len(primary_ids) == 27,
        "supplementary_count_is_6": len(supplementary_ids) == 6,
        "primary_and_supplementary_partition_graph": primary_ids
        | supplementary_ids
        == set(graph_ids)
        and primary_ids.isdisjoint(supplementary_ids),
        "split_roles_preserved": set(
            provisional_split["cohorts"]["primary_downstream"]["dev_ids"]
            + provisional_split["cohorts"]["supplementary"]["dev_ids"]
        )
        == set(graph["dev_ids"]),
    }
    integrity_ready = all_scenes_pass and all(task_gates.values()) and all(
        nesting_gates.values()
    )

    frozen_split_bytes: bytes | None = None
    if integrity_ready:
        frozen_split = deepcopy(provisional_split)
        frozen_split["manifest_version"] = 1
        frozen_split["task"] = "T04"
        frozen_split["status"] = "frozen_after_t04_integrity"
        frozen_split["not_frozen"] = False
        frozen_split["source"]["provisional_split_path"] = (
            "data/manifests/p0_provisional_split.json"
        )
        frozen_split["source"]["provisional_split_sha256"] = sha256(
            serialize_json(provisional_split)
        ).hexdigest()
        frozen_split["freeze_gate"] = {
            "integrity_manifest": "data/manifests/p0_data_integrity.json",
            "all_33_scenes_passed": True,
            "primary_task_manifest": (
                "data/manifests/p0_primary_task_manifest.jsonl"
            ),
            "primary_task_manifest_sha256": sha256(primary_bytes).hexdigest(),
            "supplementary_task_manifest": (
                "data/manifests/p0_supplementary_task_manifest.jsonl"
            ),
            "supplementary_task_manifest_sha256": sha256(
                supplementary_bytes
            ).hexdigest(),
        }
        frozen_split["next_gate"] = (
            "T05 selects and freezes the P0 CPDAG-producing SCD method; frozen "
            "scene/task membership cannot change without a new experiment version."
        )
        frozen_split_bytes = serialize_json(frozen_split)

    integrity_manifest = {
        "manifest_version": 1,
        "task": "T04",
        "status": "complete" if integrity_ready else "failed",
        "integrity_ready": integrity_ready,
        "source": {
            "benchmark": "CausalDS",
            "github_commit": source_manifest["pins"]["github"]["commit"],
            "huggingface_revision": source_manifest["pins"]["huggingface"][
                "revision"
            ],
            "provisional_split": "data/manifests/p0_provisional_split.json",
            "provisional_split_sha256": sha256(
                serialize_json(provisional_split)
            ).hexdigest(),
            "parquet_engine": f"pyarrow {pa.__version__}",
        },
        "scope": {
            "graph_scenes": 33,
            "public_parquets_read": ["data.parquet", "test_features.parquet"],
            "grading_parquets_read": [],
            "grading_metadata_read": ["ground_truth.json"],
            "duplicate_rows_are_informational": True,
        },
        "aggregate": aggregate,
        "task_gates": task_gates,
        "nesting_gates": nesting_gates,
        "scene_results": scene_results,
        "outputs": {
            "primary_task_manifest": {
                "path": "data/manifests/p0_primary_task_manifest.jsonl",
                "records": len(primary_records),
                "sha256": sha256(primary_bytes).hexdigest(),
            },
            "supplementary_task_manifest": {
                "path": "data/manifests/p0_supplementary_task_manifest.jsonl",
                "records": len(supplementary_records),
                "sha256": sha256(supplementary_bytes).hexdigest(),
            },
            "frozen_split": (
                {
                    "path": "data/manifests/p0_frozen_split.json",
                    "sha256": sha256(frozen_split_bytes).hexdigest(),
                }
                if frozen_split_bytes is not None
                else None
            ),
        },
        "verdict": {
            "integrity_ready": integrity_ready,
            "reason": (
                "All 33 graph scenes passed parquet, schema, mapping, graph, task, "
                "and public/grading-boundary gates; nested scene and task manifests "
                "are frozen for P0."
                if integrity_ready
                else "At least one required T04 integrity gate failed; split remains provisional."
            ),
        },
    }
    return {
        "integrity": serialize_json(integrity_manifest),
        "primary_tasks": primary_bytes,
        "supplementary_tasks": supplementary_bytes,
        "frozen_split": frozen_split_bytes,
    }
