"""Freeze or byte-check the offline T21 Amendment v3-A protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402


PROTOCOL = ROOT / "configs/p1_edge_selective_v2.yaml"
SCHEMA = ROOT / "schemas/p1_edge_selective_protocol_v2.schema.json"
REPORT = ROOT / "reports/t21_v3a_edge_selective_protocol.md"
OUTPUT = ROOT / "data/manifests/t21_v3a_edge_selective_protocol_freeze.json"


def yaml_obj(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return value


def json_obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_hex(path.read_bytes()),
        "bytes": path.stat().st_size,
    }


def validate(protocol: dict[str, Any], schema: dict[str, Any]) -> None:
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise RuntimeError("Protocol meta-schema drift")
    if schema.get("$id") != "https://fourgraph.local/schemas/p1_edge_selective_protocol_v2.schema.json":
        raise RuntimeError("Protocol schema ID drift")
    required = set(schema["required"])
    if set(protocol) != required:
        raise RuntimeError("Protocol has missing or unknown top-level fields")
    experiment = protocol["experiment"]
    if experiment["task"] != "T21_AMENDMENT_V3A" or experiment["status"] != "design_frozen_pre_implementation":
        raise RuntimeError("T21 v3-A lifecycle drift")

    parent = protocol["parent_graph"]
    required_parent = {
        "source": "G_SCD_RAW",
        "algorithm": "BOSS",
        "graph_type": "cpdag",
        "mutable_edge_class": "undirected_only",
        "preserve_skeleton": True,
        "preserve_compelled_directions": True,
        "add_edges": False,
        "delete_edges": False,
        "reverse_compelled_edges": False,
    }
    for key, expected in required_parent.items():
        if parent.get(key) != expected:
            raise RuntimeError(f"Parent-graph boundary drift: {key}")

    semantic = protocol["semantic_signal"]
    if semantic["model_snapshot"] != "gpt-5.4-nano-2026-03-17":
        raise RuntimeError("Semantic model snapshot drift")
    if semantic["prompt"] != "prompts/p1_semantic_preferences_v2.md":
        raise RuntimeError("Semantic prompt drift")
    if semantic["story_variants"] != ["full", "partial", "ambiguous"]:
        raise RuntimeError("Semantic evidence variants drift")
    if semantic["live_calls_authorized_at_v3a"] is not False:
        raise RuntimeError("T21 v3-A cannot authorize live calls")

    consensus = protocol["credible_extension_consensus"]
    if consensus["extension_universe"] != "all_consistent_dag_extensions_of_parent_cpdag":
        raise RuntimeError("Extension universe drift")
    if consensus["enumeration"] != "exact" or consensus["normalization"]["temperature"] != 1.0:
        raise RuntimeError("Credible-extension scoring drift")
    if consensus["normalization"]["temperature_tuning_allowed"] is not False:
        raise RuntimeError("Temperature tuning must remain forbidden")
    if consensus["joint_selection"]["greedy_order_dependence_allowed"] is not False:
        raise RuntimeError("Edge selection must be exact and order-independent")

    output = protocol["partial_graph_output"]
    if output["representation"] != "maximally_oriented_pdag_with_background_knowledge":
        raise RuntimeError("Partial-graph representation drift")
    if output["closure"]["method"] != "meek_rules_R1_R2_R3_R4":
        raise RuntimeError("Meek closure drift")
    if output["direction_sources"] != ["compelled", "semantic_selected", "closure_propagated", "unresolved"]:
        raise RuntimeError("Direction provenance vocabulary drift")

    selection = protocol["threshold_selection"]
    semantic_grid = selection["grid"]["semantic_confidence"]
    global_grid = selection["grid"]["global_stability"]
    if semantic_grid != [0.80, 0.90, 0.95, 0.99, 0.999]:
        raise RuntimeError("Semantic-confidence grid drift")
    if global_grid != [0.80, 0.90, 0.95, 1.00]:
        raise RuntimeError("Global-stability grid drift")
    if selection["candidates"] != len(semantic_grid) * len(global_grid) or selection["candidates"] != 20:
        raise RuntimeError("Threshold candidate count drift")
    gate = selection["gate"]
    expected_gate = {
        "graph_validity": 1.0,
        "end_to_end_selective_orientation_precision_minimum": 0.95,
        "minimum_answered_edges": 20,
        "minimum_orientation_coverage": 0.20,
    }
    if gate != expected_gate or selection["downstream_results_allowed_for_selection"] is not False:
        raise RuntimeError("Validation gate drift")
    if selection["no_eligible_action"] != "stop_p1_v2_without_holdout_access":
        raise RuntimeError("Fail-closed action drift")

    metrics = protocol["metric_contract"]
    if metrics["answered_direction_definition"]["include"] != ["semantic_selected", "closure_propagated"]:
        raise RuntimeError("Answered-direction numerator drift")
    if metrics["primary_precision"]["false_adjacency_orientation"] != "incorrect":
        raise RuntimeError("False adjacencies must count as incorrect")
    if metrics["coverage"]["denominator"] != "all_parent_undirected_edges_including_false_adjacencies":
        raise RuntimeError("Coverage denominator drift")

    cohorts = protocol["cohorts"]
    development = cohorts["method_development"]
    validation = cohorts["threshold_validation"]
    holdout = cohorts["final_holdout"]
    if development["threshold_selection_allowed"] is not False:
        raise RuntimeError("Observed development results cannot select the new threshold")
    if validation["count"] != 20 or validation["master_seed"] != 21301:
        raise RuntimeError("New validation cohort drift")
    if sum(validation["node_count_allocation"]) != 20:
        raise RuntimeError("Validation node-count allocation drift")
    if sum(validation["primary_motif_allocation"].values()) != 20:
        raise RuntimeError("Validation motif allocation drift")
    if sum(validation["noise_family_allocation"].values()) != 20:
        raise RuntimeError("Validation noise allocation drift")
    if sum(validation["query_strata_allocation"].values()) != 20:
        raise RuntimeError("Validation query-stratum allocation drift")
    if validation["generated_at_v3a"] or validation["method_executed_at_v3a"]:
        raise RuntimeError("T21 v3-A cannot generate or execute validation scenes")
    if holdout != {
        "source": "existing_T18_holdout_80",
        "count": 80,
        "exact_ids_unchanged": True,
        "accessed_at_v3a": False,
        "access_authorized": False,
    }:
        raise RuntimeError("Final holdout boundary drift")

    boundary = protocol["access_and_freeze"]
    forbidden_truthy = [
        boundary["v3a_api_calls"],
        boundary["v3a_validation_scenes_generated"],
        boundary["v3a_edge_selective_implemented"],
        boundary["v3a_existing_development_method_results_reanalyzed"],
        boundary["v3a_holdout_scene_artifacts_accessed"],
        boundary["v3a_holdout_method_results_accessed"],
        boundary["P1_holdout_execution_authorized"],
    ]
    if any(forbidden_truthy):
        raise RuntimeError("T21 v3-A execution boundary drift")
    if boundary["next_authorized_action"] != "T21_V3B_OFFLINE_IMPLEMENTATION_AND_SYNTHETIC_CONFORMANCE":
        raise RuntimeError("Next-action authorization drift")


def build() -> bytes:
    protocol = yaml_obj(PROTOCOL)
    schema = json_obj(SCHEMA)
    validate(protocol, schema)

    parent = json_obj(ROOT / "data/manifests/t21_v2_comparator_audit.json")
    parent_verdict = parent["verdict"]
    if parent_verdict != {
        "conformance_passed": True,
        "further_prompt_tuning_authorized": False,
        "t21_v2_passed": False,
        "t22_authorized": False,
        "threshold_gate_passed": False,
    }:
        raise RuntimeError("T21 v2 terminal verdict does not authorize a fresh protocol")

    dependency_paths = [ROOT / item for item in protocol["dependencies"]]
    if len(dependency_paths) != len(set(dependency_paths)):
        raise RuntimeError("Duplicate protocol dependency")
    if any(not path.is_file() for path in dependency_paths):
        raise RuntimeError("Missing protocol dependency")
    if any("data/generated" in path.as_posix() or "results/raw" in path.as_posix() for path in dependency_paths):
        raise RuntimeError("Protocol freeze cannot depend on raw scene or provider artifacts")

    manifest = {
        "schema_version": "fourgraph.t21_v3a_edge_selective_protocol_freeze.v1",
        "task": "T21 Amendment v3-A",
        "experiment_id": protocol["experiment"]["id"],
        "parent_terminal_audit": entry(ROOT / "data/manifests/t21_v2_comparator_audit.json"),
        "protocol": entry(PROTOCOL),
        "protocol_schema": entry(SCHEMA),
        "report": entry(REPORT),
        "dependencies": [entry(path) for path in dependency_paths],
        "implementation": entry(ROOT / "scripts/freeze_t21_v3a_edge_selective_protocol.py"),
        "design_summary": {
            "method": "G_HYBRID_H2_EDGE_SELECTIVE",
            "parent": "BOSS raw CPDAG",
            "mutable_edge_class": "undirected_only",
            "consistent_extension_enumeration": "exact",
            "threshold_candidates": 20,
            "development_scenes_for_engineering": 20,
            "new_validation_scenes": 20,
            "untouched_final_holdout_scenes": 80,
            "validation_master_seed": 21301,
            "semantic_model_snapshot": "gpt-5.4-nano-2026-03-17",
            "semantic_prompt": "p1_semantic_preferences_v2",
            "minimum_precision": 0.95,
            "minimum_answered_edges": 20,
            "minimum_coverage": 0.20,
        },
        "frozen_metric_semantics": {
            "parent_compelled_edges_excluded_from_selective_precision": True,
            "semantic_and_closure_directions_included": True,
            "oriented_false_adjacency_counts_as_incorrect": True,
            "coverage_denominator_includes_all_parent_undirected_edges": True,
            "threshold_selection_uses_downstream_results": False,
        },
        "unresolved_until_later_registered_stage": {
            "partial_graph_contract_implementation_hash": "T21_V3B",
            "production_and_independent_solver_hashes": "T21_V3B",
            "synthetic_conformance_hashes": "T21_V3B",
            "new_validation_scene_ids_and_artifact_hashes": "T21_V3C",
            "validation_semantic_response_hashes": "T21_V3D",
            "selected_threshold_or_terminal_failure": "T21_V3E",
            "holdout_execution_manifest": "T22_only_after_T21_V3E_pass",
        },
        "evidence_boundary": {
            "api_calls": 0,
            "validation_scenes_generated": 0,
            "edge_selective_implemented": False,
            "existing_development_results_reanalyzed": False,
            "holdout_scene_artifacts_accessed": 0,
            "holdout_method_results_accessed": 0,
            "holdout_ids_changed": False,
        },
        "verdict": {
            "t21_v3a_complete": True,
            "p1_v2_edge_selective_protocol_frozen": True,
            "t21_v3b_offline_implementation_authorized": True,
            "validation_generation_authorized": False,
            "live_model_calls_authorized": False,
            "t22_authorized": False,
            "p1_holdout_authorized": False,
        },
    }
    return canonical_json_bytes(manifest, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != payload:
            raise RuntimeError("T21 v3-A protocol freeze differs byte-for-byte")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(payload)
    print(json.dumps(json.loads(payload)["verdict"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
