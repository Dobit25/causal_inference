"""Evaluate frozen T08--T10 development graphs against grading-only Oracle DAGs."""

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

from fourgraph.causalds_oracle import load_causalds_oracle_graph  # noqa: E402
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex, validate_hybrid_relationship, validate_projection_relationship  # noqa: E402
from fourgraph.graph_metrics import evaluate_graph, hybrid_attribution, load_graph_artifact_jsonl  # noqa: E402


DEFAULT_CONFIG = Path("configs/t11_graph_metrics.yaml")


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _mapping(path: Path, *, yaml_file: bool = False) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if yaml_file else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def _validate_config(config: dict[str, Any]) -> None:
    scope = config["scope"]
    if scope["role"] != "dev" or scope["forbid_holdout_access"] is not True:
        raise ValueError("T11 is restricted to frozen development scenes")
    for key in ("allow_builder_tuning", "allow_llm_calls", "allow_tasks_or_queries"):
        if scope[key] is not False:
            raise ValueError(f"T11 forbidden scope enabled: {key}")
    expected = [
        ("G_LLM", "llm_dag", "primary"),
        ("G_SCD_RAW", "scd_raw_cpdag", "primary"),
        ("G_SCD_PROJECTED", "scd_projected_dag", "sensitivity"),
        ("G_HYBRID", "hybrid_dag", "primary"),
        ("G_ORACLE", "oracle", "sanity"),
    ]
    actual = [(item["id"], item["input"], item["role"]) for item in config["conditions"]]
    if actual != expected:
        raise ValueError("T11 condition order/roles changed")
    if config["inputs"]["oracle_access"] != "grading_only_in_memory" or config["inputs"]["persist_oracle_edges"] is not False:
        raise ValueError("T11 Oracle evidence boundary changed")
    functional = config["functional_metrics"]
    if functional["unavailable_is_not_zero"] is not True or any(functional[name]["status"] != "unavailable" for name in ("sid", "aid")):
        raise ValueError("T11 SID/AID compatibility decision changed")


def _validate_record_shape(record: dict[str, Any]) -> None:
    required = {
        "schema_version", "scene_id", "graph_condition", "evaluation_role",
        "graph_method", "graph_type", "graph_view", "graph_schema_version",
        "variable_mapping_sha256", "graph_sha256", "graph_artifact_sha256",
        "oracle_graph_sha256", "oracle_artifact_sha256", "node_count",
        "graph_valid", "node_set_consistent", "skeleton", "cpdag", "dag",
        "functional", "hybrid_attribution",
    }
    if set(record) != required:
        raise ValueError("T11 metric record has missing or unknown fields")
    if record["graph_type"] == "cpdag" and (record["cpdag"] is None or record["dag"] is not None):
        raise ValueError("Raw CPDAG record has invalid metric applicability")
    if record["graph_type"] == "dag" and (record["dag"] is None or record["cpdag"] is not None):
        raise ValueError("DAG record has invalid metric applicability")
    if any(record["functional"][name]["status"] != "unavailable" or record["functional"][name]["value"] is not None for name in ("sid", "aid")):
        raise ValueError("Unavailable SID/AID must be null, never zero")
    if (record["graph_condition"] == "G_HYBRID") != (record["hybrid_attribution"] is not None):
        raise ValueError("Hybrid attribution must appear only on G_HYBRID")


def _mean(records: list[dict[str, Any]], family: str) -> dict[str, float]:
    first = next(record[family] for record in records if record[family] is not None)
    return {
        key: round(sum(float(record[family][key]) for record in records) / len(records), 8)
        for key in first
    }


def _summaries(records: list[dict[str, Any]], condition_order: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for condition in condition_order:
        selected = [record for record in records if record["graph_condition"] == condition]
        graph_type = selected[0]["graph_type"]
        result[condition] = {
            "scene_count": len(selected),
            "evaluation_role": selected[0]["evaluation_role"],
            "graph_type": graph_type,
            "scene_macro_skeleton": _mean(selected, "skeleton"),
            "scene_macro_cpdag": _mean(selected, "cpdag") if graph_type == "cpdag" else None,
            "scene_macro_dag": _mean(selected, "dag") if graph_type == "dag" else None,
        }
    return result


def build_outputs(source_root: Path, *, config_path: Path = DEFAULT_CONFIG) -> tuple[bytes, bytes]:
    config = _mapping(config_path, yaml_file=True)
    _validate_config(config)
    for relative, expected in config["freeze_anchors"].items():
        if file_sha256(PROJECT_ROOT / relative) != expected:
            raise RuntimeError(f"Frozen dependency changed: {relative}")

    scope = config["scope"]
    split_path = PROJECT_ROOT / scope["split_manifest"]
    split = _mapping(split_path)
    cohort = split["cohorts"][scope["cohort"]]
    dev_ids = tuple(cohort["dev_ids"])
    holdout_ids = set(cohort["holdout_ids"])
    if len(dev_ids) != scope["expected_scenes"] or set(dev_ids) & holdout_ids:
        raise ValueError("T11 frozen development scope is invalid")

    inputs = config["inputs"]
    graphs = {
        "G_LLM": load_graph_artifact_jsonl(PROJECT_ROOT / inputs["llm_dag"]),
        "G_SCD_RAW": load_graph_artifact_jsonl(PROJECT_ROOT / inputs["scd_raw_cpdag"]),
        "G_SCD_PROJECTED": load_graph_artifact_jsonl(PROJECT_ROOT / inputs["scd_projected_dag"]),
        "G_HYBRID": load_graph_artifact_jsonl(PROJECT_ROOT / inputs["hybrid_dag"]),
    }
    if any(set(items) != set(dev_ids) for items in graphs.values()):
        raise RuntimeError("A frozen graph input does not contain exactly the dev scene set")

    oracle_config_path = PROJECT_ROOT / inputs["oracle_loader_config"]
    oracle_config_sha256 = file_sha256(oracle_config_path)
    oracles = {}
    variable_maps = {}
    oracle_input_audit = []
    for scene_id in dev_ids:
        if scene_id in holdout_ids:
            raise RuntimeError(f"T11 attempted holdout access: {scene_id}")
        loaded = load_causalds_oracle_graph(source_root, scene_id, config_sha256=oracle_config_sha256)
        oracles[scene_id] = loaded.graph_artifact
        variable_maps[scene_id] = loaded.variable_map
        oracle_input_audit.append(loaded.audit_record())

    records: list[dict[str, Any]] = []
    attributions = []
    condition_specs = {item["id"]: item for item in config["conditions"]}
    condition_order = [item["id"] for item in config["conditions"]]
    for scene_id in dev_ids:
        raw = graphs["G_SCD_RAW"][scene_id]
        projected = graphs["G_SCD_PROJECTED"][scene_id]
        hybrid = graphs["G_HYBRID"][scene_id]
        oracle = oracles[scene_id]
        validate_projection_relationship(raw, projected)
        validate_hybrid_relationship(raw, hybrid)
        attribution = hybrid_attribution(raw, projected, hybrid, oracle)
        attributions.append({"scene_id": scene_id, **attribution})
        scene_graphs = {**{key: value[scene_id] for key, value in graphs.items()}, "G_ORACLE": oracle}
        for condition in condition_order:
            record = evaluate_graph(
                scene_graphs[condition], oracle,
                condition=condition,
                role=condition_specs[condition]["role"],
                variable_mapping_sha256=variable_maps[scene_id].mapping_sha256,
                hybrid_error_attribution=attribution if condition == "G_HYBRID" else None,
            )
            _validate_record_shape(record)
            records.append(record)

    if len(records) != scope["expected_records"]:
        raise RuntimeError("T11 metric record count changed")
    records_bytes = b"".join(canonical_json_bytes(record, newline=True) for record in records)
    pooled_attribution = {
        key: sum(item[key] for item in attributions)
        for key in attributions[0]
        if key != "scene_id"
    }
    input_paths = {
        key: {"path": path, "sha256": file_sha256(PROJECT_ROOT / path)}
        for key, path in inputs.items()
        if key in {"llm_dag", "scd_raw_cpdag", "scd_projected_dag", "hybrid_dag", "oracle_loader_config"}
    }
    audit = {
        "manifest_version": 1,
        "task": "T11",
        "status": "complete_development_graph_metrics",
        "scope": {
            "cohort": "graph_dev",
            "scene_ids": list(dev_ids),
            "scene_count": len(dev_ids),
            "conditions_per_scene": len(condition_order),
            "record_count": len(records),
            "holdout_scene_count": len(holdout_ids),
            "holdout_accessed": False,
            "llm_calls_made": 0,
            "tasks_or_queries_accessed": False,
            "builder_tuning_performed": False,
            "oracle_edges_persisted": False,
        },
        "contract": {
            "config_sha256": file_sha256(config_path),
            "metric_schema_version": "fourgraph.graph_metric_record.v1",
            "metric_schema_sha256": file_sha256(PROJECT_ROOT / "schemas/graph_metric_record_v1.schema.json"),
            "graph_schema_version": "fourgraph.graph.v1",
            "metrics_input": "GraphArtifact.metrics_view",
            "split_manifest_sha256": file_sha256(split_path),
            "records_sha256": sha256_hex(records_bytes),
            "dag_shd_reversal_cost": 1,
            "normalization_denominator": "n_choose_2",
            "aggregation_unit": "scene",
        },
        "inputs": input_paths,
        "oracle_input_audit": oracle_input_audit,
        "scene_macro_summaries": _summaries(records, condition_order),
        "hybrid_attribution": {
            "by_scene": attributions,
            "pooled_counts": pooled_attribution,
        },
        "functional_metric_compatibility": {
            "sid": {"status": "unavailable", "value": None, "reason": "no_pinned_validated_implementation"},
            "aid": {"status": "unavailable", "value": None, "reason": "no_pinned_validated_implementation"},
            "raw_cpdag_silently_projected": False,
            "outcome_e_treatment": "unavailable_not_zero",
        },
        "freeze_checks": {
            "all_input_scene_sets_exact": True,
            "all_node_sets_consistent": True,
            "all_projection_parent_relationships_valid": True,
            "all_hybrid_parent_relationships_valid": True,
            "hybrid_skeleton_matches_raw_scd": True,
            "t08_t09_t10_artifacts_modified": False,
        },
        "verdict": {
            "t11_complete": True,
            "structural_graph_metrics_ready": True,
            "sid_aid_ready": False,
            "blocker": None,
        },
    }
    return records_bytes, canonical_json_bytes(audit, newline=True)


def _check(path: Path, expected: bytes) -> None:
    if not path.is_file() or path.read_bytes() != expected:
        raise RuntimeError(f"Generated artifact is missing or stale: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--records-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config_path = PROJECT_ROOT / args.config
    config = _mapping(config_path, yaml_file=True)
    records_path = PROJECT_ROOT / (args.records_output or Path(config["outputs"]["records"]))
    audit_path = PROJECT_ROOT / (args.audit_output or Path(config["outputs"]["audit"]))
    records_bytes, audit_bytes = build_outputs(args.source_root.resolve(), config_path=config_path)
    if args.check:
        _check(records_path, records_bytes)
        _check(audit_path, audit_bytes)
    else:
        records_path.parent.mkdir(parents=True, exist_ok=True)
        records_path.write_bytes(records_bytes)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_bytes(audit_bytes)
    audit = json.loads(audit_bytes)
    print(json.dumps({
        "mode": "check" if args.check else "write",
        "status": audit["status"],
        "scenes": audit["scope"]["scene_count"],
        "records": audit["scope"]["record_count"],
        "holdout_accessed": audit["scope"]["holdout_accessed"],
        "t11_complete": audit["verdict"]["t11_complete"],
        "sid_aid_ready": audit["verdict"]["sid_aid_ready"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
