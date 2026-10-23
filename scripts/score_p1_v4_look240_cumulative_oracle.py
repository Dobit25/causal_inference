"""Authorized cumulative Oracle scoring for P1V4 calibration look 240."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT)]

import replay_p1_v4_independent_calibration_look120_overlay_oracle as base
from fourgraph.p1_generation import scene_scm_record
from fourgraph.partial_graph import PartialGraph
from materialize_p1_v4_stage3 import build_blueprint

CFG = ROOT / "configs/p1_v4_look240_cumulative_oracle_scoring_execution_freeze.yaml"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(payload)


def require_hashes(entries: dict[str, dict]) -> None:
    for name, spec in entries.items():
        path = ROOT / spec["path"]
        if not path.is_file() or sha256(path) != spec["sha256"]:
            raise RuntimeError(f"input hash drift: {name}")


def build_artifacts(config: dict) -> tuple[dict[Path, bytes], dict]:
    require_hashes(config["inputs"])
    if sha256(Path(__file__)) != config["implementation"]["scorer_sha256"]:
        raise RuntimeError("scorer hash drift")

    auth_path = ROOT / config["authorization"]["path"]
    auth_audit_path = ROOT / config["authorization"]["audit_path"]
    if not auth_path.is_file() or not auth_audit_path.is_file():
        raise RuntimeError("live authorization artifacts missing")
    authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    authorization_audit = json.loads(auth_audit_path.read_text(encoding="utf-8"))
    if authorization.get("status") != "AUTHORIZED_CALIBRATION_LOOK240_ORACLE_SCORING":
        raise RuntimeError("look 240 Oracle scoring is not authorized")
    if authorization_audit.get("status") != "PASS":
        raise RuntimeError("look 200 authorization audit failed")
    execution_freeze_path = ROOT / config["execution_freeze"]["path"]
    if authorization.get("execution_freeze_sha256") != sha256(execution_freeze_path):
        raise RuntimeError("authorization does not target this execution freeze")

    checkpoint = json.loads((ROOT / config["inputs"]["checkpoint"]["path"]).read_text(encoding="utf-8"))
    ids = authorization["scope"]["exact_scene_ids"]
    stage_ids = checkpoint["scene_ids_by_stage"]
    old_ids = set(stage_ids["look120"])
    if ids != checkpoint["exact_scene_ids"] or len(ids) != 240:
        raise RuntimeError("scene scope drift")
    if (len(stage_ids["look120"]), len(stage_ids["look160"]), len(stage_ids["look200"]), len(stage_ids["look240"])) != (120, 40, 40, 40):
        raise RuntimeError("registered-look partition drift")

    parents: dict[tuple[str, str], dict] = {}
    for item in checkpoint["parent_graph_inventory"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise RuntimeError(f"parent hash drift: {item['scene_id']}/{item['condition']}")
        parents[(item["scene_id"], item["condition"])] = json.loads(path.read_text(encoding="utf-8"))["graph"]
    if len(parents) != 480:
        raise RuntimeError("parent scope drift")

    pools: dict[str, dict[str, tuple[str, str]]] = {}
    for key in ("look120_semantic_plan", "look160_semantic_plan", "look200_semantic_plan", "look240_semantic_plan"):
        plan = json.loads((ROOT / config["inputs"][key]["path"]).read_text(encoding="utf-8"))
        for scene_id, row in plan["pair_pools"].items():
            pools[scene_id] = {
                pair["pair_id"]: (pair["node_a_canonical"], pair["node_b_canonical"])
                for pair in row["pairs"]
            }
    if set(pools) != set(ids):
        raise RuntimeError("semantic pair-pool scope drift")

    groups_list: list[dict] = []
    for key in ("look120_groups", "look160_groups", "look200_groups", "look240_groups"):
        groups_list.extend(jsonl(ROOT / config["inputs"][key]["path"]))
    groups = {(row["scene_id"], row["variant"], row["pair_id"]): row for row in groups_list}
    if len(groups) != config["scope"]["exact_six_vote_groups"] or len(groups) != len(groups_list):
        raise RuntimeError("six-vote group scope or uniqueness drift")

    generation = yaml.safe_load((ROOT / config["inputs"]["generation_config"]["path"]).read_text())["generation"]
    identities = {
        row["study_id"]: row
        for row in jsonl(ROOT / config["inputs"]["exact_identities"]["path"])
    }
    materialized: dict[str, dict] = {}
    for key in ("look120_materialization", "look160_materialization", "look200_materialization", "look240_materialization"):
        payload = json.loads((ROOT / config["inputs"][key]["path"]).read_text(encoding="utf-8"))
        materialized.update({row["study_id"]: row for row in payload["records"]})

    oracles: dict[str, set[tuple[str, str]]] = {}
    commitments: dict[str, str] = {}
    for scene_id in ids:
        blueprint = build_blueprint(identities[scene_id], generation)
        commitment = hashlib.sha256(canonical_bytes(scene_scm_record(blueprint))).hexdigest().upper()
        metadata = json.loads((ROOT / materialized[scene_id]["metadata_path"]).read_text(encoding="utf-8"))
        if commitment != metadata.get("scm_commitment_sha256") or commitment != materialized[scene_id]["scm_commitment_sha256"]:
            raise RuntimeError(f"Oracle commitment mismatch: {scene_id}")
        oracles[scene_id] = set(blueprint.dag.directed)
        commitments[scene_id] = commitment

    records: list[dict] = []
    overlays: list[dict] = []
    automatic = set(config["scope"]["automatic_agreements"])
    for condition in config["scope"]["parent_conditions"]:
        for scene_id in ids:
            graph = parents[(scene_id, condition)]
            parent = PartialGraph.build(
                graph["nodes"],
                [tuple(edge) for edge in graph["directed"]],
                [tuple(edge) for edge in graph["undirected"]],
            )
            variants = ["full", "partial"] + (["ambiguous"] if scene_id in old_ids else [])
            for variant in variants:
                scene_groups = {
                    pair_id: groups[(scene_id, variant, pair_id)]
                    for pair_id in pools[scene_id]
                }
                scene_records, overlay = base.scene_output(
                    parent,
                    pools[scene_id],
                    scene_groups,
                    oracles[scene_id],
                    scene_id=scene_id,
                    condition=condition,
                    variant=variant,
                    automatic=automatic,
                )
                records.extend(scene_records)
                overlays.append(overlay)

    gates = config["sequential_gates"]
    results: dict[str, dict] = {}
    curves: dict[str, dict] = {}
    for condition in config["scope"]["parent_conditions"]:
        condition_records = [row for row in records if row["condition"] == condition]
        variant_results: dict[str, dict] = {}
        for variant in config["scope"]["certification_variants"]:
            rows = [row for row in condition_records if row["variant"] == variant]
            condition_overlays = [
                row for row in overlays
                if row["condition"] == condition and row["variant"] == variant
            ]
            scene_coverage: list[float] = []
            scene_loss: list[float] = []
            high_scene_loss: list[float] = []
            for scene_id in ids:
                scene_rows = [row for row in rows if row["scene_id"] == scene_id]
                published = [row for row in scene_rows if row["published"]]
                scene_coverage.append(len(published) / len(scene_rows))
                if published:
                    scene_loss.append(sum(not bool(row["oracle_match"]) for row in published) / len(published))
                high = [row for row in published if row["agreement"] == config["scope"]["high_agreement"]]
                if high:
                    high_scene_loss.append(sum(not bool(row["oracle_match"]) for row in high) / len(high))

            precision = base.risk(scene_loss, gates["risk"]["error_ceiling"], gates["risk"]["alternatives"], gates["risk"]["alpha_per_policy"])
            coverage = base.coverage(scene_coverage, gates["coverage"]["floor"], gates["coverage"]["alternatives"], gates["coverage"]["alpha_per_policy"])
            high_guardrail = base.risk(high_scene_loss, gates["high_guardrail"]["error_ceiling"], gates["high_guardrail"]["alternatives"], gates["high_guardrail"]["alpha"])
            precision_pass = precision["contributing_scenes"] >= gates["risk"]["minimum_contributing_scenes"] and precision["crosses"]
            high_pass = high_guardrail["contributing_scenes"] >= gates["high_guardrail"]["minimum_contributing_scenes"] and high_guardrail["crosses"]
            validity_pass = len(condition_overlays) == 240
            variant_results[variant] = {
                "certified_compelled": base.summary(rows, "certified_compelled"),
                "semantic_selected": base.summary(rows, "semantic_selected"),
                "combined_published": base.summary(rows),
                "coverage": coverage,
                "abstention_rate_scene_mean": 1.0 - coverage["mean_coverage"],
                "precision_confidence_sequence": {**precision, "precision_floor": 0.95, "pass": precision_pass},
                "High_guardrail": {**high_guardrail, "pass": high_pass},
                "overlay_validity": {
                    "valid_after_fail_closed": len(condition_overlays),
                    "total": 240,
                    "pass": validity_pass,
                    "pre_suppression_conflicts": sum(not row["semantic_overlay_valid"] for row in condition_overlays),
                },
                "false_positive_adjacency_orientations": sum(
                    row["oracle_relationship"] == "FALSE_ADJACENCY"
                    for row in rows if row["published"]
                ),
                "registered_gate_pass": precision_pass and coverage["crosses"] and high_pass and validity_pass,
            }
            curves[f"{condition}/{variant}"] = {
                "scene_coverage": scene_coverage,
                "scene_error_on_contributing": scene_loss,
                "high_scene_error": high_scene_loss,
                "precision": precision,
                "coverage": coverage,
                "High": high_guardrail,
            }

        ambiguous_rows = [
            row for row in condition_records
            if row["variant"] == "ambiguous" and row["source"] == "semantic_selected"
        ]
        flags = [
            float(any(row["published"] for row in ambiguous_rows if row["scene_id"] == scene_id))
            for scene_id in sorted(old_ids)
        ]
        ambiguous = base.risk(flags, gates["ambiguous"]["error_ceiling"], gates["ambiguous"]["alternatives"], gates["ambiguous"]["alpha"])
        results[condition] = {
            "variants": variant_results,
            "ambiguous_abstention_diagnostic": {
                "scenes": 120,
                "eligible_parent_undirected_records": len(ambiguous_rows),
                "automatic_direction_scenes": int(sum(flags)),
                "risk": ambiguous,
                "pass": ambiguous["crosses"],
            },
        }

    primary = config["scope"]["primary_parent"]
    remaining = config["scope"]["maximum_calibration_scenes"] - 240
    futility: dict[str, dict] = {}
    for variant in config["scope"]["certification_variants"]:
        curve = curves[f"{primary}/{variant}"]
        best_precision = base.risk(curve["scene_error_on_contributing"] + [0.0] * remaining, gates["risk"]["error_ceiling"], gates["risk"]["alternatives"], gates["risk"]["alpha_per_policy"])
        best_coverage = base.coverage(curve["scene_coverage"] + [1.0] * remaining, gates["coverage"]["floor"], gates["coverage"]["alternatives"], gates["coverage"]["alpha_per_policy"])
        best_high = base.risk(curve["high_scene_error"] + [0.0] * remaining, gates["high_guardrail"]["error_ceiling"], gates["high_guardrail"]["alternatives"], gates["high_guardrail"]["alpha"])
        futility[variant] = {
            "best_case_by_440": {"precision": best_precision, "coverage": best_coverage, "High": best_high},
            "futile": not (best_precision["crosses"] and best_coverage["crosses"] and best_high["crosses"]),
        }

    primary_result = results[primary]
    early = all(row["registered_gate_pass"] for row in primary_result["variants"].values()) and primary_result["ambiguous_abstention_diagnostic"]["pass"]
    status = (
        "PASS_EARLY_CERTIFICATION" if early
        else "STOP_FOR_FUTILITY" if any(row["futile"] for row in futility.values())
        else "CONTINUE_TO_LOOK_280"
    )

    dataset_bytes = b"".join(canonical_bytes(row) for row in records)
    overlay_bytes = b"".join(canonical_bytes(row) for row in overlays)
    result = {
        "schema_version": "fourgraph.p1_v4_look240_cumulative_overlay_oracle_results.v1",
        "task": config["task"],
        "status": status,
        "registered_look": 240,
        "primary_condition": primary,
        "conditions": results,
        "futility": futility,
        "selection_performed": False,
        "oracle_scope": "P1V4 calibration 240 only",
        "metric_dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest().upper(),
        "overlay_outputs_sha256": hashlib.sha256(overlay_bytes).hexdigest().upper(),
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "meek_closure": 0,
        "validation_access": 0,
        "holdout_access": 0,
    }
    audit = {
        "schema_version": "fourgraph.p1_v4_look240_cumulative_overlay_oracle_audit.v1",
        "task": config["task"],
        "status": "PASS_ORACLE_SCORING",
        "execution_freeze_sha256": sha256(execution_freeze_path),
        "authorization_sha256": sha256(auth_path),
        "authorization_audit_sha256": sha256(auth_audit_path),
        "oracle_scenes_accessed": 240,
        "oracle_commitments_verified": len(commitments),
        "metric_records": len(records),
        "overlay_outputs": len(overlays),
        "parent_cpdag_mutations": 0,
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "meek_closure": 0,
        "validation_access": 0,
        "holdout_access": 0,
        "metric_dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest().upper(),
        "overlay_outputs_sha256": hashlib.sha256(overlay_bytes).hexdigest().upper(),
    }
    report = (
        "# P1V4 cumulative calibration look 240 Oracle scoring\n\n"
        f"Status: **{status}**. Exactly 240 calibration Oracle commitments were reconstructed and verified. "
        "No semantic API call, statistical rerun, closure, validation or holdout access occurred.\n"
    ).encode()
    artifacts = {
        ROOT / config["outputs"]["metric_dataset"]: dataset_bytes,
        ROOT / config["outputs"]["overlay_outputs"]: overlay_bytes,
        ROOT / config["outputs"]["results"]: canonical_bytes(result),
        ROOT / config["outputs"]["risk_coverage"]: canonical_bytes(curves),
        ROOT / config["outputs"]["audit"]: canonical_bytes(audit),
        ROOT / config["outputs"]["report"]: report,
    }
    return artifacts, {"status": status, "audit": audit, "primary": results[primary]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.execute == args.check:
        raise SystemExit("choose exactly one of --execute or --check")
    config = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    artifacts, summary = build_artifacts(config)
    if args.check:
        for path, payload in artifacts.items():
            if not path.is_file() or path.read_bytes() != payload:
                raise RuntimeError(f"replay drift: {path}")
    else:
        for path, payload in artifacts.items():
            write_immutable(path, payload)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
