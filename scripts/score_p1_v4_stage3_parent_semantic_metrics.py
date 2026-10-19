"""Score frozen constrained parents plus semantic-selected directions, with no closure."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from fourgraph.partial_graph import PartialGraph, consistent_extension, unshielded_colliders, validate_cpdag  # noqa: E402
from fourgraph.p1_generation import scene_scm_record  # noqa: E402
from materialize_p1_v4_stage3 import build_blueprint  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_stage3_parent_semantic_metric_oracle_authorization.yaml"
PREFLIGHT = ROOT / "configs/p1_v4_stage3_method_development_preflight.yaml"
IDENTITIES = ROOT / "data/manifests/p1_v4_stage3_exact_identities.jsonl"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def oracle_dags(scene_ids: set[str]) -> dict[str, set[tuple[str, str]]]:
    generation = yaml.safe_load(PREFLIGHT.read_text(encoding="utf-8"))["generation"]
    identities = [row for row in read_jsonl(IDENTITIES) if row.get("study_id") in scene_ids]
    if {row["study_id"] for row in identities} != scene_ids:
        raise RuntimeError("exact development identity scope mismatch")
    result: dict[str, set[tuple[str, str]]] = {}
    for identity in identities:
        blueprint = build_blueprint(identity, generation)
        commitment = hashlib.sha256(canonical(scene_scm_record(blueprint))).hexdigest().upper()
        metadata_path = ROOT / "data/generated/p1_v4_stage3_method_development_cau" / identity["study_id"] / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if commitment != metadata.get("scm_commitment_sha256"):
            raise RuntimeError(f"Oracle commitment mismatch: {identity['study_id']}")
        result[identity["study_id"]] = set(blueprint.dag.directed)
    return result


def compatible(parent: PartialGraph, selected: list[tuple[str, str]]) -> tuple[bool, str | None]:
    try:
        proposal = PartialGraph.build(
            parent.nodes,
            set(parent.directed) | set(selected),
            set(parent.undirected) - {tuple(sorted(edge)) for edge in selected},
        )
        extension = consistent_extension(proposal)
    except ValueError as exc:
        return False, str(exc)
    if not parent.directed.issubset(extension.directed):
        return False, "consistent extension reversed a parent compelled direction"
    if unshielded_colliders(extension) != unshielded_colliders(parent):
        return False, "selected semantic directions change parent unshielded colliders"
    return True, None


def summary(records: list[dict[str, Any]], *, source: str | None = None) -> dict[str, Any]:
    chosen = [r for r in records if (source is None or r["source"] == source) and r["published"]]
    correct = sum(r["oracle_match"] is True for r in chosen)
    wrong = sum(r["oracle_match"] is False for r in chosen)
    return {"published": len(chosen), "correct": correct, "wrong": wrong, "precision": correct / len(chosen) if chosen else None}


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    auth_path = ROOT / cfg["outputs"]["authorization"]
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    if auth.get("status") != "AUTHORIZED_DEVELOPMENT_ORACLE_METRIC_EXECUTION" or not auth.get("explicit_user_authorization"):
        raise RuntimeError("explicit parent/semantic Oracle authorization absent")
    if auth.get("config_sha256") != sha(CONFIG):
        raise RuntimeError("authorization config drift")
    checkpoint_path = ROOT / cfg["parent_checkpoint"]["path"]
    if auth.get("checkpoint_sha256") != sha(checkpoint_path):
        raise RuntimeError("checkpoint drift")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    parent_manifest_path = ROOT / checkpoint["parent_manifest_sha256"] if False else ROOT / "data/manifests/p1_v4_stage3_parent_cpdag_metric_inputs.json"
    if sha(parent_manifest_path) != checkpoint["parent_manifest_sha256"]:
        raise RuntimeError("frozen parent manifest drift")
    parent_manifest = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    scene_ids = {f"P1V4SD{i:03d}" for i in range(30)}
    if cfg["scope"]["scenes"] != "P1V4SD000-P1V4SD029":
        raise RuntimeError("unauthorized scene scope")
    oracles = oracle_dags(scene_ids)
    pools_path = ROOT / checkpoint["parents"]["pair_pools"]["path"]
    if sha(pools_path) != checkpoint["parents"]["pair_pools"]["sha256"]:
        raise RuntimeError("pair pool drift")
    pools = {row["study_id"]: row for row in json.loads(pools_path.read_text(encoding="utf-8"))["records"]}
    group_paths = {
        "nano_medium": checkpoint["parents"]["nano_six_vote_groups"],
        "mini_medium": checkpoint["parents"]["mini_six_vote_groups"],
    }
    all_records: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    result_models: dict[str, Any] = {}
    for model, item in group_paths.items():
        group_path = ROOT / item["path"]
        if sha(group_path) != item["sha256"]:
            raise RuntimeError(f"six-vote group drift: {model}")
        groups = read_jsonl(group_path)
        groups_by_key = {(r["scene_id"], r["variant"], r["pair_id"]): r for r in groups}
        if len(groups_by_key) != len(groups):
            raise RuntimeError("duplicate six-vote group")
        model_result: dict[str, Any] = {}
        for condition in cfg["scope"]["parents"]:
            condition_records: list[dict[str, Any]] = []
            parent_rows = parent_manifest["conditions"][condition]
            parent_summary_records: list[dict[str, Any]] = []
            for scene_id in sorted(scene_ids):
                parent_graph = parent_rows[scene_id]["graph"]
                parent = PartialGraph.build(parent_graph["nodes"], [tuple(x) for x in parent_graph["directed"]], [tuple(x) for x in parent_graph["undirected"]])
                validate_cpdag(parent)
                for edge in sorted(parent.directed):
                    rec = {"schema_version": "fourgraph.p1_v4_parent_semantic_direction_metric_record.v1", "model": model, "condition": condition, "scene_id": scene_id, "variant": "parent_only", "source": "compelled", "edge": list(edge), "published": True, "oracle_match": edge in oracles[scene_id], "parent_state": "directed", "failure_status": None}
                    parent_summary_records.append(rec)
                pool = {p["pair_id"]: p for p in pools[scene_id]["shared_union_pairs"]}
                for variant in cfg["scope"]["variants"]:
                    candidate: list[tuple[str, str]] = []
                    filtered_out = 0
                    for pair_id, pair in pool.items():
                        group = groups_by_key.get((scene_id, variant, pair_id))
                        if group is None:
                            continue
                        if not group["automatic_candidate"] or group.get("candidate_direction") not in {"A_TO_B", "B_TO_A"}:
                            continue
                        undirected = tuple(sorted((pair["node_a_id"], pair["node_b_id"])))
                        if undirected not in parent.undirected:
                            filtered_out += 1
                            continue
                        candidate.append((pair["node_a_id"], pair["node_b_id"]) if group["candidate_direction"] == "A_TO_B" else (pair["node_b_id"], pair["node_a_id"]))
                    is_compatible, reason = compatible(parent, candidate)
                    selected = candidate if is_compatible else []
                    status = "PASS" if is_compatible else "FAIL_CLOSED_GLOBAL_CONFLICT"
                    for edge in sorted(parent.directed):
                        condition_records.append({"schema_version": "fourgraph.p1_v4_parent_semantic_direction_metric_record.v1", "model": model, "condition": condition, "scene_id": scene_id, "variant": variant, "source": "compelled", "edge": list(edge), "published": True, "oracle_match": edge in oracles[scene_id], "parent_state": "directed", "failure_status": status if not is_compatible else None})
                    for edge in candidate:
                        condition_records.append({"schema_version": "fourgraph.p1_v4_parent_semantic_direction_metric_record.v1", "model": model, "condition": condition, "scene_id": scene_id, "variant": variant, "source": "semantic_selected", "edge": list(edge), "published": edge in selected, "oracle_match": edge in oracles[scene_id] if edge in selected else None, "parent_state": "undirected", "failure_status": None if is_compatible else status})
                    outputs.append({"schema_version": "fourgraph.p1_v4_parent_semantic_partial_graph_output.v1", "model": model, "condition": condition, "scene_id": scene_id, "variant": variant, "status": status, "failure_reason": reason, "parent_graph": parent.to_dict(), "semantic_candidates": [list(e) for e in candidate], "semantic_selected": [list(e) for e in selected], "filtered_out_of_parent": filtered_out, "partial_graph": PartialGraph.build(parent.nodes, set(parent.directed) | set(selected), set(parent.undirected) - {tuple(sorted(e)) for e in selected}).to_dict()})
            parent_stats = summary(parent_summary_records, source="compelled")
            variant_stats: dict[str, Any] = {"parent_compelled": parent_stats}
            for variant in cfg["scope"]["variants"]:
                rows = [r for r in condition_records if r["variant"] == variant]
                semantic_stats = summary(rows, source="semantic_selected")
                end_stats = summary(rows)
                total_undirected = sum(len(parent_rows[s]["graph"]["undirected"]) for s in scene_ids)
                output_rows = [r for r in outputs if r["model"] == model and r["condition"] == condition and r["variant"] == variant]
                variant_stats[variant] = {"semantic_selected": semantic_stats, "semantic_selected_coverage_of_parent_undirected": semantic_stats["published"] / total_undirected if total_undirected else None, "end_to_end_partial_graph": {**end_stats, "unresolved_parent_edges": total_undirected - semantic_stats["published"], "unresolved_fraction_of_parent_undirected": 1 - semantic_stats["published"] / total_undirected if total_undirected else None}, "parent_undirected_edges": total_undirected, "parent_fail_closed": 0, "global_conflict_fail_closed": sum(r["status"] == "FAIL_CLOSED_GLOBAL_CONFLICT" for r in output_rows), "out_of_parent_directions_filtered": sum(r["filtered_out_of_parent"] for r in output_rows)}
            model_result[condition] = variant_stats
            all_records.extend(parent_summary_records + condition_records)
        result_models[model] = model_result
    dataset_path = ROOT / cfg["outputs"]["metric_dataset"]
    dataset_path.write_bytes(b"".join(canonical(r) for r in all_records))
    outputs_path = ROOT / cfg["outputs"]["integrated_outputs"]
    outputs_path.write_bytes(b"".join(canonical(r) for r in outputs))
    results = {"schema_version": "fourgraph.p1_v4_stage3_parent_semantic_metric_results.v1", "task": cfg["task"], "status": "PASS_DEVELOPMENT_ONLY", "models": result_models, "metric_dataset_sha256": sha(dataset_path), "integrated_outputs_sha256": sha(outputs_path), "oracle_scope": "P1V4SD000-P1V4SD029 development only", "closure": 0, "semantic_api_calls": 0, "statistical_reruns": 0, "holdout_access": 0}
    results_path = ROOT / cfg["outputs"]["results"]
    results_path.write_bytes(canonical(results))
    audit = {"schema_version": "fourgraph.p1_v4_stage3_parent_semantic_metric_audit.v1", "task": cfg["task"], "status": "PASS", "authorization_sha256": sha(auth_path), "metric_dataset_sha256": sha(dataset_path), "integrated_outputs_sha256": sha(outputs_path), "results_sha256": sha(results_path), "oracle_scenes_accessed": 30, "oracle_replay_commitments_passed": 30, "parent_cpdag_valid": {"Constrained-BOSS": 30, "Constrained-FGES": 30}, "semantic_api_calls": 0, "statistical_reruns": 0, "closure": 0, "holdout_access": 0}
    audit_path = ROOT / cfg["outputs"]["audit"]
    audit_path.write_bytes(canonical(audit))
    report_lines = ["# P1V4 parent CPDAG + semantic-selected metrics", "", "Development-only Oracle diagnostic. The integrated graph includes parent compelled directions and condition-specific `VERY_HIGH/HIGH` semantic-selected directions; no Meek closure was applied.", "", "```json", json.dumps(result_models, ensure_ascii=False, indent=2), "```", ""]
    (ROOT / cfg["outputs"]["report"]).write_text("\n".join(report_lines), encoding="utf-8")
    print(json.dumps({"models": result_models, "audit": audit}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
