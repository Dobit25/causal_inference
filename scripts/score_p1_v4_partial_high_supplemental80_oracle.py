"""Authorize and score the registered 80-scene Partial-HIGH supplement.

The freeze stage is Oracle-blind. Execute verifies the frozen inputs, then
continues the original 440-scene e-process without resetting alpha.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import replay_p1_v4_independent_calibration_look120_overlay_oracle as base
from fourgraph.p1_generation import scene_scm_record
from fourgraph.partial_graph import PartialGraph
from materialize_p1_v4_stage3 import build_blueprint

PREFIX = "p1_v4_partial_high_supplemental80"
MANIFESTS = ROOT / "data/manifests"
CHECKPOINT = MANIFESTS / f"{PREFIX}_oracle_scoring_checkpoint.json"
CONFIG = ROOT / "configs" / f"{PREFIX}_oracle_scoring.json"
AUTH = MANIFESTS / f"{PREFIX}_oracle_scoring_live_authorization.json"
AUTH_AUDIT = MANIFESTS / f"{PREFIX}_oracle_scoring_authorization_audit.json"
SCRIPT = Path(__file__).resolve()

INPUT_PATHS = {
    "protocol": MANIFESTS / f"{PREFIX}_protocol.json",
    "inference_design": MANIFESTS / f"{PREFIX}_inference_audit.json",
    "response_freeze": MANIFESTS / f"{PREFIX}_response_freeze.json",
    "response_freeze_audit": MANIFESTS / f"{PREFIX}_response_freeze_rescore_audit.json",
    "groups": MANIFESTS / f"{PREFIX}_six_vote_groups.jsonl",
    "pairs": MANIFESTS / f"{PREFIX}_pair_records.jsonl",
    "semantic_plan": MANIFESTS / f"{PREFIX}_mini_semantic_plan.json",
    "statistical_plan": MANIFESTS / f"{PREFIX}_statistical_plan.json",
    "statistical_audit": MANIFESTS / f"{PREFIX}_statistical_execution_audit.json",
    "materialization": MANIFESTS / f"{PREFIX}_materialization.json",
    "exact_identities": MANIFESTS / f"{PREFIX}_exact_identities.jsonl",
    "generation_config": ROOT / "configs/p1_v4_stage3_method_development_preflight.yaml",
    "blueprint_builder": ROOT / "scripts/materialize_p1_v4_stage3.py",
    "overlay_scorer": ROOT / "scripts/replay_p1_v4_independent_calibration_look120_overlay_oracle.py",
    "overlay_contract": MANIFESTS / "p1_v4_look120_evidence_annotated_partial_graph_contract_amendment.json",
    "historical_config": ROOT / "configs/p1_v4_look440_cumulative_oracle_scoring.yaml",
    "historical_results": MANIFESTS / "p1_v4_look440_cumulative_overlay_oracle_metric_results.json",
    "historical_curves": MANIFESTS / "p1_v4_look440_cumulative_overlay_oracle_risk_coverage.json",
    "historical_audit": MANIFESTS / "p1_v4_look440_cumulative_overlay_oracle_metric_audit.json",
    "historical_review": MANIFESTS / "p1_v4_look440_final_calibration_review.json",
    "historical_checkpoint": MANIFESTS / "p1_v4_look440_cumulative_oracle_scoring_checkpoint.json",
}


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def spec(path: Path) -> dict[str, str]:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_immutable(path: Path, body: bytes, check_only: bool = False) -> None:
    if check_only:
        if not path.is_file() or path.read_bytes() != body:
            raise RuntimeError(f"byte replay mismatch: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"existing artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)


def inventory() -> tuple[list[str], list[dict], list[dict]]:
    response = load(INPUT_PATHS["response_freeze_audit"])
    stat = load(INPUT_PATHS["statistical_audit"])
    if response.get("status") != "PASS" or response.get("effective_logical_responses") != 960:
        raise RuntimeError("response-freeze audit is not PASS")
    if response.get("production_reference_disagreements") or response.get("oracle_access"):
        raise RuntimeError("response freeze boundary violation")
    if stat.get("status") != "PASS_STATISTICAL_EXECUTION" or stat.get("complete_terminal_records") != 16480:
        raise RuntimeError("statistical audit is not PASS")
    ids = load(INPUT_PATHS["statistical_plan"])["scene_ids"]
    identities = rows(INPUT_PATHS["exact_identities"])
    materialized = load(INPUT_PATHS["materialization"])["records"]
    if len(ids) != 80 or len(set(ids)) != 80 or set(ids) != {r["study_id"] for r in identities} or set(ids) != {r["study_id"] for r in materialized}:
        raise RuntimeError("exact supplemental identity mismatch")
    old = load(INPUT_PATHS["historical_checkpoint"])["exact_scene_ids"]
    if len(old) != 440 or set(ids) & set(old):
        raise RuntimeError("historical/supplemental cohort overlap")
    plan = load(INPUT_PATHS["statistical_plan"])
    graph_items: list[dict] = []
    for job in plan["jobs"]:
        if job["algorithm"] not in ("Constrained-BOSS", "Constrained-FGES"):
            continue
        path = ROOT / "results/raw" / PREFIX / "statistical/normalized" / f"{job['execution_id']}.json"
        graph = load(path)
        if graph.get("status") != "VALID" or graph.get("job") != job:
            raise RuntimeError(f"invalid constrained parent: {job}")
        graph_items.append({"scene_id": job["scene_id"], "condition": job["algorithm"],
                            "execution_id": job["execution_id"], **spec(path)})
    if len(graph_items) != 160 or len({(r["scene_id"], r["condition"]) for r in graph_items}) != 160:
        raise RuntimeError("parent graph inventory drift")
    groups = rows(INPUT_PATHS["groups"])
    if len(groups) != 1088 or len({(r["scene_id"], r["variant"], r["pair_id"]) for r in groups}) != 1088:
        raise RuntimeError("six-vote group identity drift")
    return ids, graph_items, groups


def freeze(check_only: bool = False) -> dict:
    protocol = load(INPUT_PATHS["protocol"])
    inference = load(INPUT_PATHS["inference_design"])
    historical_review = load(INPUT_PATHS["historical_review"])
    historical_config = load(INPUT_PATHS["historical_config"])
    if historical_review.get("decision") != "STOP_FOR_FUTILITY" or protocol.get("historical_look440_decision") != "STOP_FOR_FUTILITY":
        raise RuntimeError("historical decision drift")
    if inference.get("status") != "PASS_OFFLINE_INFERENCE_DESIGN" or historical_config["scope"]["registered_look"] != 440:
        raise RuntimeError("registered inference design drift")
    if inference["same_betting_components_and_alphas"] != historical_config["sequential_gates"]:
        raise RuntimeError("e-process component/alpha drift")
    history_pin = yaml.safe_load((ROOT / "configs/p1_v4_partial_high_supplemental80_protocol.yaml").read_text(encoding="utf-8"))["historical_inputs"]
    for name, source in (("review", "historical_review"), ("results", "historical_results"), ("audit", "historical_audit")):
        if sha(INPUT_PATHS[source]) != history_pin[name]["sha256"]:
            raise RuntimeError(f"historical {name} hash drift")
    ids, parents, groups = inventory()
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_oracle_checkpoint.v1",
        "status": "PASS_READY", "exact_supplemental_scene_ids": ids,
        "historical_scene_count": 440, "supplemental_scene_count": 80,
        "parent_graph_inventory": parents,
        "six_vote_groups": len(groups), "pair_records": 6528,
        "response_freeze_audit_sha256": sha(INPUT_PATHS["response_freeze_audit"]),
        "oracle_access_before_execution": 0, "validation_access": 0, "holdout_access": 0,
    }
    checkpoint_body = canonical(checkpoint)
    write_immutable(CHECKPOINT, checkpoint_body, check_only)
    inputs = {name: spec(path) for name, path in INPUT_PATHS.items()}
    inputs["checkpoint"] = spec(CHECKPOINT)
    config = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_oracle_execution.v1",
        "status": "FROZEN_AUTHORIZED", "implementation": spec(SCRIPT),
        "inputs": inputs,
        "scope": {"supplemental_scenes": 80, "historical_scenes": 440,
                  "combined_scenes": 520, "parent_conditions": ["Constrained-BOSS", "Constrained-FGES"],
                  "primary_parent": "Constrained-BOSS", "variants": ["full", "partial"],
                  "automatic_agreements": ["VERY_HIGH", "HIGH"],
                  "High_guardrail_minimum_contributing_scenes": 60,
                  "no_new_ambiguous_or_nonedge_calls": True},
        "sequential_gates": historical_config["sequential_gates"],
        "authorization": {"explicit_user_authorization": True,
                          "authorized_after_response_freeze_PASS": True,
                          "exact_oracle_scene_ids": ids},
        "outputs": {
            "supplemental_dataset": f"data/manifests/{PREFIX}_overlay_oracle_metric_dataset.jsonl",
            "supplemental_overlays": f"data/manifests/{PREFIX}_overlay_outputs.jsonl",
            "results": f"data/manifests/{PREFIX}_overlay_oracle_metric_results.json",
            "risk_coverage": f"data/manifests/{PREFIX}_overlay_oracle_risk_coverage.json",
            "audit": f"data/manifests/{PREFIX}_overlay_oracle_metric_audit.json",
            "report": f"reports/{PREFIX}_overlay_oracle_metric_results.md",
        },
        "boundaries": {"semantic_api_calls": 0, "statistical_reruns": 0,
                       "meek_closure": 0, "validation_access": 0, "holdout_access": 0},
    }
    config_body = canonical(config)
    write_immutable(CONFIG, config_body, check_only)
    authorization = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_oracle_live_authorization.v1",
        "status": "AUTHORIZED_SUPPLEMENTAL80_ORACLE_SCORING",
        "explicit_user_authorization": True,
        "response_freeze_audit_status": "PASS",
        "config_sha256": hashlib.sha256(config_body).hexdigest().upper(),
        "checkpoint_sha256": hashlib.sha256(checkpoint_body).hexdigest().upper(),
        "exact_scene_ids": ids,
        "forbidden": ["semantic_api", "statistical_rerun", "validation", "holdout", "meek_closure", "tuning"],
    }
    auth_body = canonical(authorization)
    write_immutable(AUTH, auth_body, check_only)
    audit = {"status": "PASS", "checkpoint_sha256": sha(CHECKPOINT),
             "config_sha256": sha(CONFIG), "authorization_sha256": sha(AUTH),
             "supplemental_scenes": 80, "parents": 160, "six_vote_groups": 1088,
             "oracle_access_before_execution": 0, "semantic_api_calls": 0,
             "validation_access": 0, "holdout_access": 0}
    write_immutable(AUTH_AUDIT, canonical(audit), check_only)
    return audit


def add_summary(old: dict, fresh: dict) -> dict:
    published = old["published"] + fresh["published"]
    correct = old["correct"] + fresh["correct"]
    return {"published": published, "correct": correct, "wrong": published - correct,
            "precision": correct / published if published else None,
            "one_sided_95_wilson_lower_diagnostic": base.wilson_lower(correct, published)}


def execute(check_only: bool = False) -> dict:
    config = load(CONFIG)
    if config["implementation"]["sha256"] != sha(SCRIPT):
        raise RuntimeError("scorer implementation hash drift")
    for name, item in config["inputs"].items():
        path = ROOT / item["path"]
        if not path.is_file() or sha(path) != item["sha256"]:
            raise RuntimeError(f"frozen input hash drift: {name}")
    authorization = load(AUTH)
    if authorization.get("status") != "AUTHORIZED_SUPPLEMENTAL80_ORACLE_SCORING" or authorization.get("config_sha256") != sha(CONFIG) or not authorization.get("explicit_user_authorization"):
        raise RuntimeError("Oracle authorization drift")
    ids, graph_items, groups_list = inventory()
    if authorization["exact_scene_ids"] != ids:
        raise RuntimeError("Oracle scene identity drift")
    parents = {(row["scene_id"], row["condition"]): load(ROOT / row["path"])["graph"] for row in graph_items}
    semantic_plan = load(INPUT_PATHS["semantic_plan"])
    pools = {sid: {pair["pair_id"]: (pair["node_a_canonical"], pair["node_b_canonical"])
                   for pair in row["pairs"]} for sid, row in semantic_plan["pair_pools"].items()}
    groups = {(row["scene_id"], row["variant"], row["pair_id"]): row for row in groups_list}
    identities = {row["study_id"]: row for row in rows(INPUT_PATHS["exact_identities"])}
    materialized = {row["study_id"]: row for row in load(INPUT_PATHS["materialization"])["records"]}
    generation = yaml.safe_load(INPUT_PATHS["generation_config"].read_text(encoding="utf-8"))["generation"]

    # This is the first new Oracle read in the supplemental study.
    oracles: dict[str, set[tuple[str, str]]] = {}
    commitments: dict[str, str] = {}
    for sid in ids:
        blueprint = build_blueprint(identities[sid], generation)
        commitment = hashlib.sha256(canonical(scene_scm_record(blueprint))).hexdigest().upper()
        metadata = load(ROOT / materialized[sid]["metadata_path"])
        if commitment != metadata["scm_commitment_sha256"] or commitment != materialized[sid]["scm_commitment_sha256"]:
            raise RuntimeError(f"Oracle commitment mismatch: {sid}")
        oracles[sid] = set(blueprint.dag.directed)
        commitments[sid] = commitment

    automatic = set(config["scope"]["automatic_agreements"])
    records: list[dict] = []
    overlays: list[dict] = []
    for condition in config["scope"]["parent_conditions"]:
        for sid in ids:
            graph = parents[(sid, condition)]
            parent = PartialGraph.build(graph["nodes"], [tuple(edge) for edge in graph["directed"]],
                                        [tuple(edge) for edge in graph["undirected"]])
            for variant in config["scope"]["variants"]:
                scene_groups = {pid: groups[(sid, variant, pid)] for pid in pools[sid]}
                scored, overlay = base.scene_output(parent, pools[sid], scene_groups, oracles[sid],
                                                     scene_id=sid, condition=condition, variant=variant,
                                                     automatic=automatic)
                records.extend(scored)
                overlays.append(overlay)
    if len(overlays) != 320 or len({(r["scene_id"], r["condition"], r["variant"]) for r in overlays}) != 320:
        raise RuntimeError("supplemental overlay scope drift")

    old_results = load(INPUT_PATHS["historical_results"])
    old_curves = load(INPUT_PATHS["historical_curves"])
    old_review = load(INPUT_PATHS["historical_review"])
    gates = config["sequential_gates"]
    extension: dict[str, dict] = {}
    combined: dict[str, dict] = {}
    curves: dict[str, dict] = {}
    for condition in config["scope"]["parent_conditions"]:
        extension[condition] = {"variants": {}}
        combined[condition] = {"variants": {}}
        for variant in config["scope"]["variants"]:
            current = [row for row in records if row["condition"] == condition and row["variant"] == variant]
            outputs = [row for row in overlays if row["condition"] == condition and row["variant"] == variant]
            coverages: list[float] = []
            losses: list[float] = []
            high_losses: list[float] = []
            high_scenes = 0
            for sid in ids:
                scene_rows = [row for row in current if row["scene_id"] == sid]
                if not scene_rows:
                    raise RuntimeError(f"missing parent rows: {sid}/{condition}/{variant}")
                published = [row for row in scene_rows if row["published"]]
                coverages.append(len(published) / len(scene_rows))
                if published:
                    losses.append(sum(row["oracle_match"] is not True for row in published) / len(published))
                high = [row for row in published if row["agreement"] == "HIGH"]
                if high:
                    high_scenes += 1
                    high_losses.append(sum(row["oracle_match"] is not True for row in high) / len(high))
            valid_after_suppression = all(
                output["semantic_overlay_valid"] or not any(
                    row["published"] and row["source"] == "semantic_selected"
                    for row in current if row["scene_id"] == output["scene_id"]
                ) for output in outputs
            )
            if not valid_after_suppression:
                raise RuntimeError("invalid published semantic overlay")
            fresh = {
                "scenes": 80,
                "certified_compelled": base.summary(current, "certified_compelled"),
                "semantic_selected": base.summary(current, "semantic_selected"),
                "combined_published": base.summary(current),
                "scene_mean_coverage": sum(coverages) / 80,
                "scene_mean_abstention": 1 - sum(coverages) / 80,
                "High_contributing_scenes": high_scenes,
                "High_scene_error_sum": sum(high_losses),
                "false_positive_adjacency_orientations": sum(
                    row["oracle_relationship"] == "FALSE_ADJACENCY" for row in current if row["published"]
                ),
                "overlay_validity": {"valid_after_fail_closed": 80, "total": 80,
                                     "pass": valid_after_suppression,
                                     "pre_suppression_conflicts": sum(not output["semantic_overlay_valid"] for output in outputs)},
            }
            extension[condition]["variants"][variant] = fresh
            key = f"{condition}/{variant}"
            old_curve = old_curves[key]
            old_variant = old_results["conditions"][condition]["variants"][variant]
            if len(old_curve["scene_coverage"]) != 440 or len(old_curve["high_scene_error"]) != old_variant["High_guardrail"]["contributing_scenes"]:
                raise RuntimeError("historical e-process array drift")
            joint_coverage = old_curve["scene_coverage"] + coverages
            joint_losses = old_curve["scene_error_on_contributing"] + losses
            joint_high = old_curve["high_scene_error"] + high_losses
            precision = base.risk(joint_losses, gates["risk"]["error_ceiling"],
                                  gates["risk"]["alternatives"], gates["risk"]["alpha_per_policy"])
            coverage = base.coverage(joint_coverage, gates["coverage"]["floor"],
                                     gates["coverage"]["alternatives"], gates["coverage"]["alpha_per_policy"])
            high = base.risk(joint_high, gates["high_guardrail"]["error_ceiling"],
                             gates["high_guardrail"]["alternatives"], gates["high_guardrail"]["alpha"])
            precision_pass = precision["contributing_scenes"] >= gates["risk"]["minimum_contributing_scenes"] and precision["crosses"]
            high_pass = high["contributing_scenes"] >= gates["high_guardrail"]["minimum_contributing_scenes"] and high["crosses"]
            old_valid = old_variant["overlay_validity"]
            combined[condition]["variants"][variant] = {
                "scenes": 520,
                "certified_compelled": add_summary(old_variant["certified_compelled"], fresh["certified_compelled"]),
                "semantic_selected": add_summary(old_variant["semantic_selected"], fresh["semantic_selected"]),
                "combined_published": add_summary(old_variant["combined_published"], fresh["combined_published"]),
                "precision_confidence_sequence": {**precision, "precision_floor": .95, "pass": precision_pass},
                "coverage": coverage,
                "abstention_rate_scene_mean": 1 - coverage["mean_coverage"],
                "High_guardrail": {**high, "pass": high_pass},
                "overlay_validity": {
                    "valid_after_fail_closed": old_valid["valid_after_fail_closed"] + 80,
                    "total": 520, "pass": bool(old_valid["pass"] and valid_after_suppression),
                    "pre_suppression_conflicts": old_valid["pre_suppression_conflicts"] + fresh["overlay_validity"]["pre_suppression_conflicts"],
                },
                "false_positive_adjacency_orientations": old_variant["false_positive_adjacency_orientations"] + fresh["false_positive_adjacency_orientations"],
                "registered_gate_pass": precision_pass and coverage["crosses"] and high_pass and old_valid["pass"] and valid_after_suppression,
            }
            curves[key] = {"scene_coverage": joint_coverage,
                           "scene_error_on_contributing": joint_losses,
                           "high_scene_error": joint_high,
                           "precision": precision, "coverage": coverage, "High": high}
        combined[condition]["ambiguous_abstention_diagnostic"] = old_results["conditions"][condition]["ambiguous_abstention_diagnostic"]
    primary = config["scope"]["primary_parent"]
    gate_pass = all(combined[primary]["variants"][variant]["registered_gate_pass"] for variant in ("full", "partial")) and combined[primary]["ambiguous_abstention_diagnostic"]["pass"]
    status = "PASS_SUPPLEMENTAL_CONFIRMATION" if gate_pass else "STOP_SUPPLEMENTAL_NEGATIVE_OR_INCONCLUSIVE"
    dataset_bytes = b"".join(canonical(row) for row in records)
    overlay_bytes = b"".join(canonical(row) for row in overlays)
    results = {
        "schema_version": "fourgraph.p1_v4_partial_high_supplemental80_overlay_oracle_results.v1",
        "status": status, "historical_look440_decision_unchanged": old_review["decision"],
        "historical_look440": old_results,
        "extension_only": extension,
        "combined_520": combined,
        "primary_condition": primary,
        "validation_authorized": False, "holdout_authorized": False,
        "scientific_interpretation": "supplemental_confirmation_not_retroactive_original_calibration_PASS_or_independent_replication",
        "metric_dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest().upper(),
        "overlay_outputs_sha256": hashlib.sha256(overlay_bytes).hexdigest().upper(),
        "semantic_api_calls": 0, "statistical_reruns": 0, "meek_closure": 0,
        "validation_access": 0, "holdout_access": 0,
    }
    audit = {"status": "PASS_ORACLE_SCORING", "decision": status,
             "oracle_scenes_accessed": 80, "oracle_commitments_verified": len(commitments),
             "metric_records": len(records), "overlay_outputs": len(overlays),
             "parent_cpdag_mutations": 0, "semantic_api_calls": 0,
             "statistical_reruns": 0, "meek_closure": 0,
             "validation_access": 0, "holdout_access": 0,
             "metric_dataset_sha256": results["metric_dataset_sha256"],
             "overlay_outputs_sha256": results["overlay_outputs_sha256"]}
    new_partial_high = extension[primary]["variants"]["partial"]["High_contributing_scenes"]
    joint_partial_high = combined[primary]["variants"]["partial"]["High_guardrail"]["contributing_scenes"]
    report = (
        "# P1V4 Partial-HIGH supplemental-80 Oracle scoring\n\n"
        f"Decision: **{status}**. The historical look-440 result remains **{old_review['decision']}**. "
        "This is a separately registered supplement, not a retroactive original calibration PASS.\n\n"
        f"Primary Partial HIGH contributing scenes: 53 historical + {new_partial_high} new = **{joint_partial_high}** "
        f"(registered minimum 60). Full and Partial cumulative gates were evaluated with the same e-process components, "
        "mixture weights and alpha as the original 440-scene process.\n\n"
        "Only the 80 supplemental Oracle commitments were newly opened. No semantic API, statistical rerun, "
        "Meek closure, validation, or holdout was used. The fixed 120-scene Ambiguous diagnostic was carried forward "
        "without new calls. Further scenes or validation require a separate authorization.\n"
    ).encode()
    output = config["outputs"]
    artifacts = {
        ROOT / output["supplemental_dataset"]: dataset_bytes,
        ROOT / output["supplemental_overlays"]: overlay_bytes,
        ROOT / output["results"]: canonical(results),
        ROOT / output["risk_coverage"]: canonical(curves),
        ROOT / output["audit"]: canonical(audit),
        ROOT / output["report"]: report,
    }
    for path, body in artifacts.items():
        write_immutable(path, body, check_only)
    return {"status": status, "audit": audit,
            "primary_extension": extension[primary], "primary_combined": combined[primary],
            "robustness_extension": extension["Constrained-FGES"],
            "robustness_combined": combined["Constrained-FGES"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("freeze", "execute", "check"))
    args = parser.parse_args()
    result = freeze() if args.stage == "freeze" else execute(args.stage == "check")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
