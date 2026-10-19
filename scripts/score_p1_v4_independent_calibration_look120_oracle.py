"""Authorized Oracle scoring for frozen P1V4 calibration look 120.

The scorer has no API or discovery adapter.  It rebuilds only the registered
calibration Oracle commitments, validates them against frozen materialization
metadata, then evaluates the frozen Mini six-vote decisions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from fourgraph.partial_graph import PartialGraph, consistent_extension  # noqa: E402
from fourgraph.p1_generation import scene_scm_record  # noqa: E402
from fourgraph.sequential_evidence import coverage_e_value, crosses, risk_e_value  # noqa: E402
from materialize_p1_v4_stage3 import build_blueprint  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_oracle_scoring_execution.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"non-deterministic artifact drift: {path}")
        return
    path.write_bytes(payload)


def wilson_lower(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    z = 1.6448536269514722
    p = correct / total
    den = 1 + z * z / total
    center = p + z * z / (2 * total)
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (center - radius) / den


def risk(losses: list[float], *, ceiling: float, alternatives: list[float], alpha: float) -> dict[str, Any]:
    if not losses:
        return {"contributing_scenes": 0, "mean_error": None, "e_value": 0.0, "crosses": False}
    e_value = float(risk_e_value(sum(losses), len(losses), ceiling, alternatives))
    return {"contributing_scenes": len(losses), "mean_error": sum(losses) / len(losses), "e_value": e_value, "crosses": bool(crosses(e_value, alpha))}


def coverage(values: list[float], *, floor: float, alternatives: list[float], alpha: float) -> dict[str, Any]:
    e_value = float(coverage_e_value(sum(values), len(values), floor, alternatives))
    return {"scenes": len(values), "mean_coverage": sum(values) / len(values), "e_value": e_value, "crosses": bool(crosses(e_value, alpha))}


def relationship(edge: tuple[str, str], oracle: set[tuple[str, str]]) -> str:
    if edge in oracle:
        return "MATCH"
    if (edge[1], edge[0]) in oracle:
        return "REVERSED"
    return "FALSE_ADJACENCY"


def load_pinned(cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    auth_path = ROOT / cfg["authorization"]["path"]
    audit_path = ROOT / cfg["authorization"]["audit_path"]
    if sha(auth_path) != cfg["authorization"]["sha256"] or sha(audit_path) != cfg["authorization"]["audit_sha256"]:
        raise RuntimeError("Oracle authorization hash drift")
    auth, auth_audit = json.loads(auth_path.read_text(encoding="utf-8")), json.loads(audit_path.read_text(encoding="utf-8"))
    if auth.get("status") != cfg["authorization"]["required_status"] or not auth.get("explicit_user_authorization"):
        raise RuntimeError("explicit Oracle scoring authorization absent")
    if auth_audit.get("metrics_calculated") != 0 or auth_audit.get("oracle_access_during_authorization") != 0:
        raise RuntimeError("authorization was not a clean pre-scoring checkpoint")
    expected = {
        "checkpoint": "checkpoint_sha256", "six_vote_groups": "six_vote_groups_sha256", "pair_records": "pair_records_sha256",
        "materialization_manifest": "materialization_manifest_sha256", "exact_identities": "exact_identities_sha256",
        "generation_config": "generation_config_sha256", "blueprint_builder": "blueprint_builder_sha256",
    }
    for name, key in expected.items():
        if sha(ROOT / cfg["inputs"][name]) != cfg["inputs"][key]:
            raise RuntimeError(f"pinned input hash drift: {name}")
    checkpoint = json.loads((ROOT / cfg["inputs"]["checkpoint"]).read_text(encoding="utf-8"))
    if checkpoint.get("status") != "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION":
        raise RuntimeError("parent checkpoint no longer eligible")
    scene_ids = list(checkpoint["scope"]["exact_scene_ids"])
    if len(scene_ids) != 120 or len(set(scene_ids)) != 120:
        raise RuntimeError("unauthorized calibration scene scope")
    inventory: dict[tuple[str, str], dict[str, Any]] = {}
    for item in checkpoint["constrained_parent_graph_inventory"]:
        key = (item["scene_id"], item["condition"])
        if key in inventory:
            raise RuntimeError("duplicate parent inventory record")
        path = ROOT / item["normalized_path"]
        if not path.is_file() or sha(path) != item["normalized_sha256"]:
            raise RuntimeError(f"parent artifact hash drift: {key}")
        inventory[key] = json.loads(path.read_text(encoding="utf-8"))
    if len(inventory) != 240:
        raise RuntimeError("constrained parent inventory cardinality drift")
    groups, pairs = jsonl(ROOT / cfg["inputs"]["six_vote_groups"]), jsonl(ROOT / cfg["inputs"]["pair_records"])
    return auth, scene_ids, checkpoint, inventory, groups, pairs


def registered_oracles(cfg: dict[str, Any], scene_ids: list[str]) -> tuple[dict[str, set[tuple[str, str]]], dict[str, str]]:
    generation = yaml.safe_load((ROOT / cfg["inputs"]["generation_config"]).read_text(encoding="utf-8"))["generation"]
    identities = {row["study_id"]: row for row in jsonl(ROOT / cfg["inputs"]["exact_identities"])}
    materialized = {row["study_id"]: row for row in json.loads((ROOT / cfg["inputs"]["materialization_manifest"]).read_text(encoding="utf-8"))["records"]}
    if set(scene_ids) - set(identities) or set(scene_ids) - set(materialized):
        raise RuntimeError("authorized scene is absent from frozen identity/materialization records")
    oracle, commitments = {}, {}
    for scene_id in scene_ids:
        blueprint = build_blueprint(identities[scene_id], generation)
        commitment = hashlib.sha256(canonical(scene_scm_record(blueprint))).hexdigest().upper()
        metadata = json.loads((ROOT / materialized[scene_id]["metadata_path"]).read_text(encoding="utf-8"))
        if commitment != materialized[scene_id]["scm_commitment_sha256"] or commitment != metadata.get("scm_commitment_sha256"):
            raise RuntimeError(f"Oracle commitment mismatch: {scene_id}")
        oracle[scene_id] = set(blueprint.dag.directed)
        commitments[scene_id] = commitment
    return oracle, commitments


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    published = [row for row in rows if row["published"]]
    correct = sum(row["oracle_match"] is True for row in published)
    wrong = len(published) - correct
    return {"published": len(published), "correct": correct, "wrong": wrong, "precision": correct / len(published) if published else None,
            "one_sided_95_wilson_lower_diagnostic": wilson_lower(correct, len(published))}


def output_for_scene_variant(*, parent: PartialGraph, groups: dict[str, dict[str, Any]], pair_map: dict[str, tuple[str, str]], oracle: set[tuple[str, str]], variant: str, condition: str, scene_id: str, automatic: set[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    directed_pairs = {tuple(sorted(edge)): edge for edge in parent.directed}
    undirected_pairs = set(parent.undirected)
    all_edges = set(directed_pairs) | undirected_pairs
    for edge_key in sorted(all_edges):
        pair_id = next((pid for pid, nodes in pair_map.items() if tuple(sorted(nodes)) == edge_key), None)
        if pair_id is None or pair_id not in groups:
            raise RuntimeError(f"missing semantic group for parent adjacency: {scene_id}/{variant}/{edge_key}")
        group = groups[pair_id]
        semantic_edge = None
        if group.get("automatic_candidate") and group.get("agreement") in automatic:
            a, b = pair_map[pair_id]
            semantic_edge = (a, b) if group.get("candidate_direction") == "A_TO_B" else (b, a)
        if edge_key in directed_pairs:
            parent_edge = directed_pairs[edge_key]
            published = semantic_edge == parent_edge
            state = "confirmed_compelled" if published else "unresolved_compelled_conflict" if semantic_edge else "unresolved_compelled_not_confirmed"
            chosen = parent_edge if published else None
            source = "confirmed_compelled"
        else:
            published = semantic_edge is not None
            state = "semantic_selected" if published else "unresolved_undirected"
            chosen = semantic_edge
            source = "semantic_selected"
        relation = relationship(chosen, oracle) if chosen else "ABSTAIN"
        decisions.append({"schema_version": "fourgraph.p1_v4_calibration_oracle_metric_record.v1", "scene_id": scene_id, "condition": condition, "variant": variant, "pair_id": pair_id,
                          "parent_edge": list(directed_pairs[edge_key] if edge_key in directed_pairs else edge_key), "parent_state": "directed" if edge_key in directed_pairs else "undirected",
                          "agreement": group["agreement"], "completeness": group["completeness"], "semantic_candidate_direction": list(semantic_edge) if semantic_edge else None,
                          "source": source, "publication_state": state, "published": published, "published_direction": list(chosen) if chosen else None,
                          "oracle_relationship": relation, "oracle_match": relation == "MATCH" if chosen else None})
    selected = [tuple(row["published_direction"]) for row in decisions if row["published"]]
    unresolved = {tuple(sorted(row["parent_edge"])) for row in decisions if not row["published"]}
    partial = PartialGraph.build(parent.nodes, selected, unresolved)
    try:
        consistent_extension(partial)
        validity, reason = True, None
    except ValueError as exc:
        validity, reason = False, str(exc)
    if not validity:
        for row in decisions:
            if row["published"]:
                row["published"] = False; row["published_direction"] = None; row["oracle_relationship"] = "FAIL_CLOSED_OUTPUT_INCONSISTENT"; row["oracle_match"] = None; row["publication_state"] = "fail_closed_output_inconsistent"
        partial = PartialGraph.build(parent.nodes, [], all_edges)
    return decisions, {"schema_version": "fourgraph.p1_v4_calibration_partial_output.v1", "scene_id": scene_id, "condition": condition, "variant": variant,
                       "output_valid": validity, "failure_reason": reason, "parent_graph": parent.to_dict(), "partial_graph": partial.to_dict(), "closure": 0}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true"); parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.execute == args.check:
        raise SystemExit("choose exactly one of --execute or --check")
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    auth, scene_ids, checkpoint, inventory, groups, pairs = load_pinned(cfg)
    if len(groups) != 2454 or len(pairs) != 14724:
        raise RuntimeError("frozen response scope cardinality drift")
    oracle, oracle_hashes = registered_oracles(cfg, scene_ids)
    pool_rows = json.loads((ROOT / checkpoint["parents"]["semantic_execution_plan"]["path"]).read_text(encoding="utf-8"))["pair_pools"]
    groups_by_key = {(row["scene_id"], row["variant"], row["pair_id"]): row for row in groups}
    if len(groups_by_key) != len(groups):
        raise RuntimeError("duplicate frozen six-vote identity")
    pool_by_scene = {scene: {pair["pair_id"]: (pair["node_a_canonical"], pair["node_b_canonical"]) for pair in value["pairs"]} for scene, value in pool_rows.items()}
    all_records: list[dict[str, Any]] = []
    partial_outputs: list[dict[str, Any]] = []
    automatic = set(cfg["scope"]["automatic_agreements"])
    for condition in cfg["scope"]["parent_conditions"]:
        for scene_id in scene_ids:
            graph = inventory[(scene_id, condition)]["graph"]
            parent = PartialGraph.build(graph["nodes"], [tuple(x) for x in graph["directed"]], [tuple(x) for x in graph["undirected"]])
            for variant in [*cfg["scope"]["certification_variants"], cfg["scope"]["diagnostic_variant"]]:
                selected_groups = {pid: groups_by_key[(scene_id, variant, pid)] for pid in pool_by_scene[scene_id]}
                decisions, output = output_for_scene_variant(parent=parent, groups=selected_groups, pair_map=pool_by_scene[scene_id], oracle=oracle[scene_id], variant=variant, condition=condition, scene_id=scene_id, automatic=automatic)
                all_records.extend(decisions); partial_outputs.append(output)

    primary = cfg["scope"]["primary_parent"]
    result_conditions: dict[str, Any] = {}
    risk_coverage: dict[str, Any] = {}
    gate = cfg["sequential_gates"]
    for condition in cfg["scope"]["parent_conditions"]:
        condition_rows = [row for row in all_records if row["condition"] == condition]
        variants: dict[str, Any] = {}
        for variant in cfg["scope"]["certification_variants"]:
            rows = [row for row in condition_rows if row["variant"] == variant]
            comp = [row for row in rows if row["source"] == "confirmed_compelled"]
            sem = [row for row in rows if row["source"] == "semantic_selected"]
            output_rows = [row for row in partial_outputs if row["condition"] == condition and row["variant"] == variant]
            scene_coverages, losses, high_losses = [], [], []
            for scene_id in scene_ids:
                scene_rows = [row for row in rows if row["scene_id"] == scene_id]
                published = [row for row in scene_rows if row["published"]]
                scene_coverages.append(len(published) / len(scene_rows))
                if published:
                    losses.append(sum(not bool(row["oracle_match"]) for row in published) / len(published))
                high = [row for row in published if row["agreement"] == cfg["scope"]["high_agreement"]]
                if high:
                    high_losses.append(sum(not bool(row["oracle_match"]) for row in high) / len(high))
            combined = summarize(rows)
            coverage_stat = coverage(scene_coverages, floor=float(gate["coverage"]["floor"]), alternatives=gate["coverage"]["alternatives"], alpha=float(gate["coverage"]["alpha_per_policy"]))
            risk_stat = risk(losses, ceiling=float(gate["risk"]["error_ceiling"]), alternatives=gate["risk"]["alternatives"], alpha=float(gate["risk"]["alpha_per_policy"]))
            high_stat = risk(high_losses, ceiling=float(gate["high_guardrail"]["error_ceiling"]), alternatives=gate["high_guardrail"]["alternatives"], alpha=float(gate["high_guardrail"]["alpha"]))
            high_pass = high_stat["contributing_scenes"] >= int(gate["high_guardrail"]["minimum_contributing_scenes"]) and high_stat["crosses"]
            precision_pass = risk_stat["contributing_scenes"] >= int(gate["risk"]["minimum_contributing_scenes"]) and risk_stat["crosses"]
            validity_pass = all(row["output_valid"] for row in output_rows)
            variants[variant] = {"confirmed_compelled": summarize(comp), "semantic_selected": summarize(sem), "end_to_end_partial_graph": combined,
                                 "coverage": coverage_stat, "abstention_rate_scene_mean": 1 - coverage_stat["mean_coverage"], "precision_evidence": risk_stat,
                                 "High_guardrail": {**high_stat, "pass": high_pass}, "graph_validity": {"valid": sum(row["output_valid"] for row in output_rows), "total": len(output_rows), "pass": validity_pass},
                                 "false_positive_adjacency_orientations": sum(row["oracle_relationship"] == "FALSE_ADJACENCY" for row in rows if row["published"]),
                                 "registered_gate_pass": precision_pass and coverage_stat["crosses"] and high_pass and validity_pass}
            risk_coverage[f"{condition}/{variant}"] = {"scene_coverage": scene_coverages, "scene_error_on_contributing": losses, "high_scene_error": high_losses,
                                                         "precision_evidence": risk_stat, "coverage": coverage_stat, "High_guardrail": high_stat}
        ambiguous_rows = [row for row in condition_rows if row["variant"] == cfg["scope"]["diagnostic_variant"] and row["parent_state"] == "undirected"]
        ambiguous_scene_flags = [float(any(row["published"] for row in ambiguous_rows if row["scene_id"] == scene_id)) for scene_id in scene_ids]
        ambiguous = risk(ambiguous_scene_flags, ceiling=float(gate["ambiguous"]["error_ceiling"]), alternatives=gate["ambiguous"]["alternatives"], alpha=float(gate["ambiguous"]["alpha"]))
        result_conditions[condition] = {"variants": variants, "ambiguous_abstention_diagnostic": {"eligible_undirected_records": len(ambiguous_rows), "automatic_direction_scenes": int(sum(ambiguous_scene_flags)), "risk": ambiguous, "pass": ambiguous["crosses"]}}

    primary_gates = result_conditions[primary]["variants"]
    primary_all_pass = all(item["registered_gate_pass"] for item in primary_gates.values()) and result_conditions[primary]["ambiguous_abstention_diagnostic"]["pass"]
    # Conservative registered futility: even perfect remaining scenes cannot cross a required e-process boundary.
    max_scenes = int(cfg["scope"]["maximum_calibration_scenes"]); remaining = max_scenes - len(scene_ids)
    futility: dict[str, Any] = {}
    for variant in cfg["scope"]["certification_variants"]:
        item = risk_coverage[f"{primary}/{variant}"]
        best_risk = risk(item["scene_error_on_contributing"] + [0.0] * remaining, ceiling=float(gate["risk"]["error_ceiling"]), alternatives=gate["risk"]["alternatives"], alpha=float(gate["risk"]["alpha_per_policy"]))
        best_coverage = coverage(item["scene_coverage"] + [1.0] * remaining, floor=float(gate["coverage"]["floor"]), alternatives=gate["coverage"]["alternatives"], alpha=float(gate["coverage"]["alpha_per_policy"]))
        best_high = risk(item["high_scene_error"] + [0.0] * remaining, ceiling=float(gate["high_guardrail"]["error_ceiling"]), alternatives=gate["high_guardrail"]["alternatives"], alpha=float(gate["high_guardrail"]["alpha"]))
        futility[variant] = {"best_case_by_440": {"precision": best_risk, "coverage": best_coverage, "High": best_high}, "futile": not (best_risk["crosses"] and best_coverage["crosses"] and best_high["crosses"])}
    status = "PASS_EARLY_CERTIFICATION" if primary_all_pass else "STOP_FOR_FUTILITY" if any(row["futile"] for row in futility.values()) else "CONTINUE_TO_REGISTERED_LOOK_160"
    dataset = b"".join(canonical(row) for row in all_records)
    outputs = b"".join(canonical(row) for row in partial_outputs)
    results = {"schema_version": "fourgraph.p1_v4_independent_calibration_look120_oracle_metric_results.v1", "task": cfg["task"], "status": status, "registered_look": 120,
               "conditions": result_conditions, "primary_condition": primary, "futility": futility, "selection_performed": False,
               "oracle_scope": "P1V4 independent calibration look120 only", "metric_dataset_sha256": hashlib.sha256(dataset).hexdigest().upper(), "partial_outputs_sha256": hashlib.sha256(outputs).hexdigest().upper(),
               "semantic_api_calls": 0, "statistical_reruns": 0, "closure": 0, "holdout_access": 0}
    audit = {"schema_version": "fourgraph.p1_v4_independent_calibration_look120_oracle_metric_audit.v1", "task": cfg["task"], "status": "PASS_ORACLE_SCORING_EXECUTION",
             "authorization_sha256": sha(ROOT / cfg["authorization"]["path"]), "oracle_scenes_accessed": len(oracle), "oracle_commitments_verified": len(oracle_hashes),
             "metric_records": len(all_records), "partial_outputs": len(partial_outputs), "parent_graph_validity_failures": 0,
             "output_graph_fail_closed": sum(not row["output_valid"] for row in partial_outputs), "semantic_api_calls": 0, "statistical_reruns": 0, "closure": 0, "holdout_access": 0,
             "metric_dataset_sha256": hashlib.sha256(dataset).hexdigest().upper(), "partial_outputs_sha256": hashlib.sha256(outputs).hexdigest().upper()}
    report = "# P1V4 independent calibration look120 Oracle scoring\n\nStatus: **%s**. This registered look scores the frozen Mini-medium outputs on only the 120 calibration Oracle commitments. It neither calls an API nor tunes the model/prompt/policy, reruns discovery, applies Meek closure, or accesses holdout data.\n" % status
    bodies = {ROOT / cfg["outputs"]["metric_dataset"]: dataset, ROOT / cfg["outputs"]["partial_outputs"]: outputs, ROOT / cfg["outputs"]["results"]: canonical(results), ROOT / cfg["outputs"]["risk_coverage"]: canonical(risk_coverage), ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report.encode("utf-8")}
    if args.check:
        for path, body in bodies.items():
            if not path.is_file() or path.read_bytes() != body:
                raise RuntimeError(f"artifact replay drift: {path}")
        print("Oracle metric artifacts reproduce byte-for-byte; no API/statistical rerun/closure/holdout.")
    else:
        for path, body in bodies.items(): write_once(path, body)
        print(json.dumps({"status": status, "audit": audit, "primary": result_conditions[primary]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
