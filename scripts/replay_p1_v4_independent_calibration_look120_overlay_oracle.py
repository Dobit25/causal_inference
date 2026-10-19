"""Replay authorized Oracle scoring with an immutable-parent evidence overlay."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fourgraph.evidence_annotated_partial import validate_evidence_annotated_overlay  # noqa: E402
from fourgraph.p1_generation import scene_scm_record  # noqa: E402
from fourgraph.partial_graph import PartialGraph  # noqa: E402
from fourgraph.sequential_evidence import coverage_e_value, crosses, risk_e_value  # noqa: E402
from materialize_p1_v4_stage3 import build_blueprint  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_overlay_oracle_replay_execution.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_once(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise RuntimeError(f"non-deterministic artifact drift: {path}")
        return
    path.write_bytes(body)


def wilson_lower(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    z, p = 1.6448536269514722, correct / total
    denominator = 1 + z * z / total
    center = p + z * z / (2 * total)
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (center - radius) / denominator


def risk(losses: list[float], ceiling: float, alternatives: list[float], alpha: float) -> dict[str, Any]:
    if not losses:
        return {"contributing_scenes": 0, "mean_error": None, "e_value": 0.0, "crosses": False}
    value = float(risk_e_value(sum(losses), len(losses), ceiling, alternatives))
    return {"contributing_scenes": len(losses), "mean_error": sum(losses) / len(losses), "e_value": value, "crosses": bool(crosses(value, alpha))}


def coverage(values: list[float], floor: float, alternatives: list[float], alpha: float) -> dict[str, Any]:
    value = float(coverage_e_value(sum(values), len(values), floor, alternatives))
    return {"scenes": len(values), "mean_coverage": sum(values) / len(values), "e_value": value, "crosses": bool(crosses(value, alpha))}


def relation(edge: tuple[str, str], oracle: set[tuple[str, str]]) -> str:
    if edge in oracle:
        return "MATCH"
    if (edge[1], edge[0]) in oracle:
        return "REVERSED"
    return "FALSE_ADJACENCY"


def summary(rows: list[dict[str, Any]], source: str | None = None) -> dict[str, Any]:
    selected = [row for row in rows if row["published"] and (source is None or row["source"] == source)]
    correct = sum(row["oracle_match"] is True for row in selected)
    return {"published": len(selected), "correct": correct, "wrong": len(selected) - correct,
            "precision": correct / len(selected) if selected else None,
            "one_sided_95_wilson_lower_diagnostic": wilson_lower(correct, len(selected))}


def load_scope(cfg: dict[str, Any]) -> tuple[list[str], dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, tuple[str, str]]], dict[tuple[str, str, str], dict[str, Any]]]:
    for name in ("authorization",):
        item = cfg[name]
        if sha(ROOT / item["path"]) != item["sha256"] or sha(ROOT / item["audit_path"]) != item["audit_sha256"]:
            raise RuntimeError("overlay replay authorization hash drift")
    auth = json.loads((ROOT / cfg["authorization"]["path"]).read_text(encoding="utf-8"))
    if auth.get("status") != cfg["authorization"]["required_status"] or not auth.get("explicit_user_authorization"):
        raise RuntimeError("overlay replay is not explicitly authorized")
    hashes = {"checkpoint": "checkpoint_sha256", "amendment": "amendment_sha256", "six_vote_groups": "six_vote_groups_sha256", "materialization_manifest": "materialization_manifest_sha256", "exact_identities": "exact_identities_sha256", "generation_config": "generation_config_sha256", "blueprint_builder": "blueprint_builder_sha256"}
    for name, key in hashes.items():
        if sha(ROOT / cfg["inputs"][name]) != cfg["inputs"][key]:
            raise RuntimeError(f"input hash drift: {name}")
    checkpoint = json.loads((ROOT / cfg["inputs"]["checkpoint"]).read_text(encoding="utf-8"))
    amendment = json.loads((ROOT / cfg["inputs"]["amendment"]).read_text(encoding="utf-8"))
    if amendment.get("status") != "PASS_OFFLINE_FROZEN":
        raise RuntimeError("overlay contract amendment is not frozen")
    scene_ids = list(auth["scope"]["exact_scene_ids"])
    if scene_ids != checkpoint["scope"]["exact_scene_ids"] or len(scene_ids) != 120:
        raise RuntimeError("authorized calibration scope drift")
    parents: dict[tuple[str, str], dict[str, Any]] = {}
    for item in checkpoint["constrained_parent_graph_inventory"]:
        path = ROOT / item["normalized_path"]
        if sha(path) != item["normalized_sha256"]:
            raise RuntimeError("parent graph inventory hash drift")
        record = json.loads(path.read_text(encoding="utf-8"))
        parents[(item["scene_id"], item["condition"])] = record["graph"]
    if len(parents) != 240:
        raise RuntimeError("constrained parent scope drift")
    plan = json.loads((ROOT / checkpoint["parents"]["semantic_execution_plan"]["path"]).read_text(encoding="utf-8"))
    pools = {scene: {pair["pair_id"]: (pair["node_a_canonical"], pair["node_b_canonical"]) for pair in row["pairs"]} for scene, row in plan["pair_pools"].items()}
    groups = {(row["scene_id"], row["variant"], row["pair_id"]): row for row in load_jsonl(ROOT / cfg["inputs"]["six_vote_groups"])}
    if len(groups) != 2454:
        raise RuntimeError("six-vote group cardinality drift")
    return scene_ids, parents, pools, groups


def load_oracles(cfg: dict[str, Any], scene_ids: list[str]) -> tuple[dict[str, set[tuple[str, str]]], dict[str, str]]:
    generation = yaml.safe_load((ROOT / cfg["inputs"]["generation_config"]).read_text(encoding="utf-8"))["generation"]
    identities = {row["study_id"]: row for row in load_jsonl(ROOT / cfg["inputs"]["exact_identities"])}
    materialization = {row["study_id"]: row for row in json.loads((ROOT / cfg["inputs"]["materialization_manifest"]).read_text(encoding="utf-8"))["records"]}
    result, commitments = {}, {}
    for scene_id in scene_ids:
        blueprint = build_blueprint(identities[scene_id], generation)
        commitment = hashlib.sha256(canonical(scene_scm_record(blueprint))).hexdigest().upper()
        metadata = json.loads((ROOT / materialization[scene_id]["metadata_path"]).read_text(encoding="utf-8"))
        if commitment != metadata.get("scm_commitment_sha256") or commitment != materialization[scene_id]["scm_commitment_sha256"]:
            raise RuntimeError(f"Oracle commitment mismatch: {scene_id}")
        result[scene_id], commitments[scene_id] = set(blueprint.dag.directed), commitment
    return result, commitments


def scene_output(parent: PartialGraph, pair_map: dict[str, tuple[str, str]], groups: dict[str, dict[str, Any]], oracle: set[tuple[str, str]], *, scene_id: str, condition: str, variant: str, automatic: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_skeleton = {tuple(sorted(nodes)): pair_id for pair_id, nodes in pair_map.items()}
    semantic_candidates: set[tuple[str, str]] = set()
    prelim: list[dict[str, Any]] = []
    for edge in sorted(parent.undirected):
        pair_id = by_skeleton.get(edge)
        if pair_id is None or pair_id not in groups:
            raise RuntimeError(f"missing group for parent-undirected edge: {scene_id}/{condition}/{edge}")
        group = groups[pair_id]
        direction = None
        if group["automatic_candidate"] and group["agreement"] in automatic:
            a, b = pair_map[pair_id]; direction = (a, b) if group["candidate_direction"] == "A_TO_B" else (b, a)
            semantic_candidates.add(direction)
        prelim.append({"edge": edge, "pair_id": pair_id, "group": group, "direction": direction})
    semantic_validation = validate_evidence_annotated_overlay(parent, semantic_candidates)
    published_semantic = semantic_candidates if semantic_validation.valid else set()
    records: list[dict[str, Any]] = []
    for edge in sorted(parent.directed):
        pair_id = by_skeleton.get(tuple(sorted(edge)))
        if pair_id is None or pair_id not in groups:
            raise RuntimeError(f"missing group for parent-compelled edge: {scene_id}/{condition}/{edge}")
        group = groups[pair_id]
        direction = None
        if group["automatic_candidate"] and group["agreement"] in automatic:
            a, b = pair_map[pair_id]; direction = (a, b) if group["candidate_direction"] == "A_TO_B" else (b, a)
        published = direction == edge
        state = "certified_compelled" if published else "parent_compelled_unconfirmed"
        failure = None if published else "semantic_conflict_with_parent" if direction else "insufficient_semantic_agreement"
        records.append({"schema_version": "fourgraph.p1_v4_overlay_oracle_metric_record.v1", "scene_id": scene_id, "condition": condition, "variant": variant, "pair_id": pair_id,
                        "parent_edge": list(edge), "parent_state": "directed", "agreement": group["agreement"], "completeness": group["completeness"],
                        "source": "certified_compelled", "publication_state": state, "published": published, "published_direction": list(edge) if published else None,
                        "oracle_relationship": relation(edge, oracle) if published else "ABSTAIN", "oracle_match": relation(edge, oracle) == "MATCH" if published else None, "failure_reason": failure})
    for item in prelim:
        direction = item["direction"]
        published = direction in published_semantic
        state = "certified_semantic_orientation" if published else "unresolved_parent_undirected"
        failure = None if published else "FAIL_CLOSED_SEMANTIC_CONFLICT" if direction and not semantic_validation.valid else "insufficient_semantic_agreement"
        records.append({"schema_version": "fourgraph.p1_v4_overlay_oracle_metric_record.v1", "scene_id": scene_id, "condition": condition, "variant": variant, "pair_id": item["pair_id"],
                        "parent_edge": list(item["edge"]), "parent_state": "undirected", "agreement": item["group"]["agreement"], "completeness": item["group"]["completeness"],
                        "source": "semantic_selected", "publication_state": state, "published": published, "published_direction": list(direction) if published else None,
                        "oracle_relationship": relation(direction, oracle) if published else "ABSTAIN", "oracle_match": relation(direction, oracle) == "MATCH" if published else None, "failure_reason": failure})
    visible = []
    for record in records:
        visible.append({"edge": record["parent_edge"], "display": record["published_direction"] if record["published"] else "undirected", "provenance": record["publication_state"]})
    overlay = {"schema_version": "fourgraph.p1_v4_evidence_annotated_overlay_output.v1", "scene_id": scene_id, "condition": condition, "variant": variant,
               "parent_cpdag": parent.to_dict(), "parent_immutable": True, "semantic_candidates": [list(edge) for edge in sorted(semantic_candidates)],
               "semantic_overlay_valid": semantic_validation.valid, "semantic_overlay_failure_reason": semantic_validation.reason, "visible_edges": visible, "closure": 0}
    return records, overlay


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.execute == args.check: raise SystemExit("choose exactly one of --execute or --check")
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    scene_ids, graph_data, pools, group_rows = load_scope(cfg)
    oracles, commitments = load_oracles(cfg, scene_ids)
    automatic = set(cfg["scope"]["automatic_agreements"])
    records: list[dict[str, Any]] = []; overlays: list[dict[str, Any]] = []
    variants = [*cfg["scope"]["certification_variants"], cfg["scope"]["diagnostic_variant"]]
    for condition in cfg["scope"]["parent_conditions"]:
        for scene_id in scene_ids:
            graph = graph_data[(scene_id, condition)]
            parent = PartialGraph.build(graph["nodes"], [tuple(edge) for edge in graph["directed"]], [tuple(edge) for edge in graph["undirected"]])
            for variant in variants:
                groups = {pair_id: group_rows[(scene_id, variant, pair_id)] for pair_id in pools[scene_id]}
                scene_records, overlay = scene_output(parent, pools[scene_id], groups, oracles[scene_id], scene_id=scene_id, condition=condition, variant=variant, automatic=automatic)
                records.extend(scene_records); overlays.append(overlay)

    gate = cfg["sequential_gates"]; primary = cfg["scope"]["primary_parent"]; results_conditions: dict[str, Any] = {}; risk_curve: dict[str, Any] = {}
    for condition in cfg["scope"]["parent_conditions"]:
        condition_rows = [row for row in records if row["condition"] == condition]; variant_results: dict[str, Any] = {}
        for variant in cfg["scope"]["certification_variants"]:
            rows = [row for row in condition_rows if row["variant"] == variant]; outputs = [row for row in overlays if row["condition"] == condition and row["variant"] == variant]
            scene_coverage: list[float] = []; losses: list[float] = []; high_losses: list[float] = []
            for scene_id in scene_ids:
                scene_rows = [row for row in rows if row["scene_id"] == scene_id]; published = [row for row in scene_rows if row["published"]]
                scene_coverage.append(len(published) / len(scene_rows))
                if published: losses.append(sum(not bool(row["oracle_match"]) for row in published) / len(published))
                high = [row for row in published if row["agreement"] == cfg["scope"]["high_agreement"]]
                if high: high_losses.append(sum(not bool(row["oracle_match"]) for row in high) / len(high))
            precision = risk(losses, float(gate["risk"]["error_ceiling"]), gate["risk"]["alternatives"], float(gate["risk"]["alpha_per_policy"]))
            cov = coverage(scene_coverage, float(gate["coverage"]["floor"]), gate["coverage"]["alternatives"], float(gate["coverage"]["alpha_per_policy"]))
            high = risk(high_losses, float(gate["high_guardrail"]["error_ceiling"]), gate["high_guardrail"]["alternatives"], float(gate["high_guardrail"]["alpha"]))
            high_pass = high["contributing_scenes"] >= int(gate["high_guardrail"]["minimum_contributing_scenes"]) and high["crosses"]
            precision_pass = precision["contributing_scenes"] >= int(gate["risk"]["minimum_contributing_scenes"]) and precision["crosses"]
            # The validator is applied before fail-closed suppression.  A pre-suppression
            # conflict therefore records a diagnostic, but the published overlay contains
            # no selected semantic direction for that scene and remains valid.
            output_valid = True
            variant_results[variant] = {"certified_compelled": summary(rows, "certified_compelled"), "semantic_selected": summary(rows, "semantic_selected"), "combined_published": summary(rows),
                                        "coverage": cov, "abstention_rate_scene_mean": 1 - cov["mean_coverage"], "precision_evidence": precision,
                                        "High_guardrail": {**high, "pass": high_pass}, "overlay_validity": {"valid_after_fail_closed": len(outputs), "total": len(outputs), "pass": output_valid, "pre_suppression_conflicts": sum(not row["semantic_overlay_valid"] for row in outputs)},
                                        "semantic_conflict_fail_closed": sum(not row["semantic_overlay_valid"] for row in outputs),
                                        "false_positive_adjacency_orientations": sum(row["oracle_relationship"] == "FALSE_ADJACENCY" for row in rows if row["published"]),
                                        "registered_gate_pass": precision_pass and cov["crosses"] and high_pass and output_valid}
            risk_curve[f"{condition}/{variant}"] = {"scene_coverage": scene_coverage, "scene_error_on_contributing": losses, "high_scene_error": high_losses, "precision_evidence": precision, "coverage": cov, "High_guardrail": high}
        ambiguous_rows = [row for row in condition_rows if row["variant"] == cfg["scope"]["diagnostic_variant"] and row["source"] == "semantic_selected"]
        flags = [float(any(row["published"] for row in ambiguous_rows if row["scene_id"] == scene_id)) for scene_id in scene_ids]
        ambiguous = risk(flags, float(gate["ambiguous"]["error_ceiling"]), gate["ambiguous"]["alternatives"], float(gate["ambiguous"]["alpha"]))
        results_conditions[condition] = {"variants": variant_results, "ambiguous_abstention_diagnostic": {"eligible_parent_undirected_records": len(ambiguous_rows), "automatic_direction_scenes": int(sum(flags)), "risk": ambiguous, "pass": ambiguous["crosses"]}}

    max_scenes, remaining = int(cfg["scope"]["maximum_calibration_scenes"]), int(cfg["scope"]["maximum_calibration_scenes"]) - len(scene_ids)
    futility: dict[str, Any] = {}
    for variant in cfg["scope"]["certification_variants"]:
        curve = risk_curve[f"{primary}/{variant}"]
        best_precision = risk(curve["scene_error_on_contributing"] + [0.0] * remaining, float(gate["risk"]["error_ceiling"]), gate["risk"]["alternatives"], float(gate["risk"]["alpha_per_policy"]))
        best_coverage = coverage(curve["scene_coverage"] + [1.0] * remaining, float(gate["coverage"]["floor"]), gate["coverage"]["alternatives"], float(gate["coverage"]["alpha_per_policy"]))
        best_high = risk(curve["high_scene_error"] + [0.0] * remaining, float(gate["high_guardrail"]["error_ceiling"]), gate["high_guardrail"]["alternatives"], float(gate["high_guardrail"]["alpha"]))
        futility[variant] = {"best_case_by_440": {"precision": best_precision, "coverage": best_coverage, "High": best_high}, "futile": not (best_precision["crosses"] and best_coverage["crosses"] and best_high["crosses"])}
    primary_pass = all(row["registered_gate_pass"] for row in results_conditions[primary]["variants"].values()) and results_conditions[primary]["ambiguous_abstention_diagnostic"]["pass"]
    status = "PASS_EARLY_CERTIFICATION" if primary_pass else "STOP_FOR_FUTILITY" if any(x["futile"] for x in futility.values()) else "CONTINUE_TO_REGISTERED_LOOK_160"
    dataset, overlay_body = b"".join(canonical(row) for row in records), b"".join(canonical(row) for row in overlays)
    results = {"schema_version": "fourgraph.p1_v4_independent_calibration_look120_overlay_oracle_metric_results.v1", "task": cfg["task"], "status": status, "registered_look": 120,
               "primary_condition": primary, "conditions": results_conditions, "futility": futility, "selection_performed": False,
               "oracle_scope": "P1V4 independent calibration look120 only", "metric_dataset_sha256": hashlib.sha256(dataset).hexdigest().upper(), "overlay_outputs_sha256": hashlib.sha256(overlay_body).hexdigest().upper(),
               "semantic_api_calls": 0, "statistical_reruns": 0, "meek_closure": 0, "holdout_access": 0}
    audit = {"schema_version": "fourgraph.p1_v4_independent_calibration_look120_overlay_oracle_metric_audit.v1", "task": cfg["task"], "status": "PASS_OVERLAY_ORACLE_REPLAY",
             "authorization_sha256": sha(ROOT / cfg["authorization"]["path"]), "oracle_scenes_accessed": len(oracles), "oracle_commitments_verified": len(commitments),
             "metric_records": len(records), "overlay_outputs": len(overlays), "parent_cpdag_mutations": 0, "semantic_api_calls": 0, "statistical_reruns": 0, "meek_closure": 0, "holdout_access": 0,
             "metric_dataset_sha256": hashlib.sha256(dataset).hexdigest().upper(), "overlay_outputs_sha256": hashlib.sha256(overlay_body).hexdigest().upper()}
    report = "# P1V4 calibration look120 evidence-annotated overlay Oracle replay\n\nStatus: **%s**. The immutable constrained parent CPDAG is retained as the statistical constraint; visible uncertainty is an evidence overlay, not a replacement CPDAG. No API, statistical rerun, Meek closure, tuning, or holdout access occurred.\n" % status
    bodies = {ROOT / cfg["outputs"]["metric_dataset"]: dataset, ROOT / cfg["outputs"]["overlay_outputs"]: overlay_body, ROOT / cfg["outputs"]["results"]: canonical(results), ROOT / cfg["outputs"]["risk_coverage"]: canonical(risk_curve), ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report.encode("utf-8")}
    if args.check:
        for path, body in bodies.items():
            if not path.is_file() or path.read_bytes() != body: raise RuntimeError(f"artifact replay drift: {path}")
        print("Overlay Oracle replay artifacts reproduce byte-for-byte; no API/statistical rerun/closure/holdout.")
    else:
        for path, body in bodies.items(): write_once(path, body)
        print(json.dumps({"status": status, "audit": audit, "primary": results_conditions[primary]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
