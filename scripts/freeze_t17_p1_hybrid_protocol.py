"""Freeze or byte-check the pre-generation P1 Hybrid research protocol."""

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


def yaml_obj(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def json_obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_hex(path.read_bytes()),
        "bytes": path.stat().st_size,
    }


def validate(protocol: dict[str, Any]) -> None:
    if protocol["schema_version"] != "fourgraph.p1_hybrid_protocol.v1":
        raise RuntimeError("P1 protocol schema drift")
    if protocol["generation"]["scene_count"] != 100:
        raise RuntimeError("P1 must contain 100 scenes")
    split = protocol["generation"]["split"]
    if split["development"] != 20 or split["holdout"] != 80:
        raise RuntimeError("P1 split must be 20/80")
    if sum(protocol["generation"]["graph"]["node_count_allocation"]) != 100:
        raise RuntimeError("Node-count allocation must cover every scene")
    graph = protocol["generation"]["graph"]
    if sum(graph["primary_motif_allocation"].values()) != 100:
        raise RuntimeError("Primary-motif allocation must cover every scene")
    if graph["candidate_generation"]["exhaustion_action"] != "fail_T18_without_replacement_or_rule_change":
        raise RuntimeError("Generator exhaustion must fail closed")
    scm = protocol["generation"]["scm"]
    if sum(scm["exogenous_noise_family_allocation"]) != 100:
        raise RuntimeError("Noise-family allocation must cover every scene")
    if len(protocol["tasks"]["task_ids"]) != 5 or protocol["tasks"]["tasks_per_scene"] != 5:
        raise RuntimeError("P1 requires the fixed five-task panel")
    if sum(protocol["tasks"]["query_target_strata"].values()) != 100:
        raise RuntimeError("Query strata must cover every scene")
    if protocol["semantic_evidence"]["variants"] != ["full", "partial", "ambiguous"]:
        raise RuntimeError("Semantic evidence variants drift")
    fractions = [protocol["semantic_evidence"][name]["directional_evidence_fraction"] for name in ("full", "partial", "ambiguous")]
    if fractions != [1.0, 0.5, 0.0]:
        raise RuntimeError("Semantic evidence dose drift")
    views = protocol["graph_views"]
    if len(views["static"]) + len(views["semantic"]) != views["structural_per_scene"] or views["structural_per_scene"] != 12:
        raise RuntimeError("Structural graph-view schedule drift")
    downstream_views = sum(bool(item.get("downstream")) for item in views["static"] + views["semantic"])
    if downstream_views != 11 or views["scheduled_counts"]["downstream_tasks_total"] != 5500:
        raise RuntimeError("Downstream graph-view schedule drift")
    if views["scheduled_counts"]["structural_total"] != 1200:
        raise RuntimeError("Structural schedule drift")
    if protocol["hybrid_methods"]["H2_SELECTIVE"]["abstain_output"] != "unchanged_G_SCD_RAW_cpdag":
        raise RuntimeError("Selective H2 must preserve raw CPDAG on abstention")
    selection = protocol["development_selection"]
    if selection["evidence_variant_weighting"] != "equal_weight_full_partial_ambiguous":
        raise RuntimeError("Development evidence-variant weighting drift")
    if selection["selection_rule"]["eligibility"]["graph_validity"] != 1.0:
        raise RuntimeError("H2 selection requires perfect graph validity")
    if selection["selection_rule"]["eligibility"]["selective_orientation_precision_minimum"] != 0.95:
        raise RuntimeError("H2 selective precision gate drift")
    if protocol["statistics"]["independent_unit"] != "scene_id" or protocol["statistics"]["bootstrap_replicates"] != 5000:
        raise RuntimeError("P1 statistical contract drift")
    boundary = protocol["access_and_freeze"]
    forbidden_truthy = [
        protocol["semantic_backend"]["live_calls_authorized_at_T17"],
        protocol["reasoner"]["live_calls_authorized_at_T17"],
        boundary["T17_api_calls"],
        boundary["T17_generated_scenes"],
        boundary["T17_h2_implemented"],
        boundary["T17_p1_holdout_accessed"],
        boundary["T18_live_llm_calls_authorized"],
        boundary["T18_h2_implementation_authorized"],
        boundary["P1_holdout_execution_authorized"],
    ]
    if any(forbidden_truthy):
        raise RuntimeError("T17 improperly authorizes P1 execution")
    if boundary["next_authorized_action"] != "T18_FRESH_SCM_GENERATOR_AND_INVENTORY":
        raise RuntimeError("T17 next action drift")
    budget = boundary["budget_policy"]
    if budget["automatic_provider_or_model_substitution"] or not budget["call_caps_must_be_frozen_per_live_stage"]:
        raise RuntimeError("Live-stage budget/model boundary drift")


def build() -> bytes:
    protocol_path = ROOT / "configs/p1_hybrid_v1.yaml"
    schema_path = ROOT / "schemas/p1_hybrid_protocol_v1.schema.json"
    report_path = ROOT / "reports/t17_p1_hybrid_protocol.md"
    protocol = yaml_obj(protocol_path)
    schema = json_obj(schema_path)
    validate(protocol)
    if schema.get("$id") != "https://fourgraph.local/schemas/p1_hybrid_protocol_v1.schema.json":
        raise RuntimeError("P1 protocol JSON schema drift")

    t16 = json_obj(ROOT / "data/manifests/t16_p0_findings_audit.json")
    if t16["verdict"]["p0_decision"] != "REFINE" or not t16["verdict"]["t17_protocol_design_authorized"]:
        raise RuntimeError("T16 does not authorize T17")
    if t16["verdict"]["p1_started"] or t16["verdict"]["p1_execution_authorized"]:
        raise RuntimeError("T16 evidence boundary drift")

    dependency_paths = [ROOT / value for value in protocol["dependencies"]]
    if len(dependency_paths) != len(set(dependency_paths)) or any(not path.is_file() for path in dependency_paths):
        raise RuntimeError("P1 dependency list is missing or duplicated")
    old_p1_path = ROOT / protocol["experiment"]["supersedes_unexecuted_design"]
    if old_p1_path not in dependency_paths:
        raise RuntimeError("Superseded P1 design must remain hash-pinned")

    manifest = {
        "schema_version": "fourgraph.t17_p1_hybrid_protocol_freeze.v1",
        "task": "T17",
        "experiment_id": protocol["experiment"]["id"],
        "parent_decision": entry(ROOT / "data/manifests/t16_p0_findings_audit.json"),
        "protocol": entry(protocol_path),
        "protocol_schema": entry(schema_path),
        "report": entry(report_path),
        "dependencies": [entry(path) for path in dependency_paths],
        "implementation": entry(ROOT / "scripts/freeze_t17_p1_hybrid_protocol.py"),
        "design_summary": {
            "scenes": 100,
            "development_scenes": 20,
            "holdout_scenes": 80,
            "semantic_variants": 3,
            "tasks_per_scene": 5,
            "structural_views_per_scene": 12,
            "downstream_views_per_scene": 11,
            "structural_records_planned": 1200,
            "downstream_records_planned": 5500,
            "primary_scd_output": "cpdag",
            "direct_lingam_role": "structural_sensitivity_only",
            "primary_hybrid": "H2_SELECTIVE",
            "abstention_representation": "unchanged_raw_cpdag",
        },
        "unresolved_until_registered_stage": {
            "exact_scene_split_ids": "T18",
            "generated_scm_and_task_hashes": "T18",
            "semantic_story_template_and_variant_hashes": "T19",
            "semantic_preference_prompt_hash": "T20",
            "H2_implementation_hashes": "T20",
            "selected_abstention_thresholds": "T21",
            "holdout_execution_manifest": "T22",
        },
        "evidence_boundary": {
            "api_calls": 0,
            "generated_scenes": 0,
            "H2_implemented": False,
            "development_results": 0,
            "holdout_accessed": False,
            "old_p1_file_modified": False,
        },
        "verdict": {
            "t17_complete": True,
            "p1_hybrid_protocol_frozen": True,
            "t18_generator_inventory_authorized": True,
            "live_model_calls_authorized": False,
            "H2_implementation_authorized": False,
            "p1_holdout_authorized": False,
        },
    }
    return canonical_json_bytes(manifest, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = ROOT / "data/manifests/t17_p1_hybrid_protocol_freeze.json"
    payload = build()
    if args.check:
        if not output.is_file() or output.read_bytes() != payload:
            raise RuntimeError("T17 protocol freeze differs byte-for-byte")
    else:
        output.write_bytes(payload)
    print(json.dumps(json.loads(payload)["verdict"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
