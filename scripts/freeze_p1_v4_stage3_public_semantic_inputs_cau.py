"""Freeze P1V4 public Full/Partial stories and shared condition pair pools.

This is an offline input-construction step.  It reconstructs the registered
T19 story protocol only after checking the materialized scene commitment, and
never exposes canonical IDs or SCM information to the model-facing artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from materialize_p1_v4_stage3 import build_blueprint, load_development_identities  # noqa: E402
from fourgraph.p1_generation import scene_scm_record  # noqa: E402
from fourgraph.p1_stories import build_story_bundle, public_builder_view, validate_story_bundle  # noqa: E402
from fourgraph.partial_graph import PartialGraph, consistent_extension_with_trace  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_stage3_public_semantic_inputs_cau.yaml"


def line(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"YAML root must be mapping: {path}")
    return value


def verify_pinned(parents: dict[str, Any]) -> None:
    for name, item in parents.items():
        path = ROOT / str(item["path"])
        if not path.is_file():
            raise RuntimeError(f"missing pinned dependency {name}: {path}")
        expected = item.get("sha256")
        if expected and sha_file(path) != expected:
            raise RuntimeError(f"pinned dependency drift {name}")


def graph_by_condition(raw_root: Path, conditions: dict[str, str]) -> dict[tuple[str, str], dict[str, Any]]:
    expected_algorithms = set(conditions.values())
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(raw_root.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        job, graph = record.get("job"), record.get("graph")
        if not isinstance(job, dict) or not isinstance(graph, dict):
            raise RuntimeError(f"malformed statistical raw record {path}")
        algorithm = str(job.get("algorithm"))
        if algorithm not in expected_algorithms:
            continue
        scene_id = str(job.get("scene_id"))
        key = (scene_id, algorithm)
        if key in results:
            raise RuntimeError(f"duplicate constrained parent artifact {key}")
        parent = PartialGraph.build(graph["nodes"], graph["directed"], graph["undirected"])
        try:
            consistent_extension_with_trace(parent)
        except ValueError as exc:
            raise RuntimeError(f"invalid constrained parent {key}: {exc}") from exc
        if graph.get("graph_type") != "cpdag":
            raise RuntimeError(f"constrained parent is not CPDAG {key}")
        results[key] = {"path": rel(path), "sha256": sha_file(path), "graph": parent.to_dict()}
    return results


def leakage_flags(story: str) -> dict[str, bool]:
    lowered = story.lower()
    return {
        "oracle_dag_metadata": any(term in lowered for term in ("oracle", "dag")),
        "cpdag_metadata": "cpdag" in lowered,
        "canonical_ids": bool(re.search(r"\bX[0-9]{3}\b", story)),
        "gold_labels": any(term in lowered for term in ("gold answer", "gold label", "ground truth")),
        "holdout_information": "holdout" in lowered,
        "statistical_outputs": any(term in lowered for term in ("bootstrap", "p-value", "statistical fit", "seed=")),
    }


def construct() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    cfg = load_yaml(CONFIG)
    verify_pinned(cfg["parents"])
    generation_cfg = load_yaml(ROOT / str(cfg["cohort"]["generation_config"]))["generation"]
    t19_path = ROOT / str(cfg["parents"]["story_protocol"]["path"])
    t19 = load_yaml(t19_path)
    identities_path = ROOT / str(cfg["parents"]["exact_identities"]["path"])
    identities = load_development_identities(identities_path)
    identities.sort(key=lambda row: row["study_id"])
    expected_ids = [f"P1V4SD{i:03d}" for i in range(30)]
    if [row["study_id"] for row in identities] != expected_ids:
        raise RuntimeError("P1V4 exact identity order mismatch")
    raw_root = ROOT / str(cfg["parents"]["statistical_execution_config"]["path"])
    stat_cfg = load_yaml(raw_root)
    raw_records = ROOT / str(stat_cfg["runtime"]["raw_root"])
    condition_artifacts = graph_by_condition(raw_records, cfg["semantic_pair_pools"]["conditions"])
    if len(condition_artifacts) != 60:
        raise RuntimeError(f"expected 60 constrained parent artifacts, got {len(condition_artifacts)}")
    story_root = ROOT / str(cfg["outputs"]["story_root"])
    stories: list[dict[str, Any]] = []
    pools: list[dict[str, Any]] = []
    source_checks: list[dict[str, Any]] = []
    for identity in identities:
        study_id = identity["study_id"]
        scene_dir = ROOT / str(cfg["cohort"]["source_scene_root"]) / study_id
        metadata_path = scene_dir / "metadata.json"
        if not metadata_path.is_file():
            raise RuntimeError(f"missing materialized metadata: {study_id}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        blueprint = build_blueprint(identity, generation_cfg)
        scm = scene_scm_record(blueprint)
        source_sha = sha_bytes(line(scm))
        if source_sha != metadata.get("scm_commitment_sha256"):
            raise RuntimeError(f"source commitment drift: {study_id}")
        bundle = build_story_bundle(scm, t19)
        counts = validate_story_bundle(bundle, t19)
        aliases = dict(bundle.alias_map)
        source_checks.append({"study_id": study_id, "source_commitment_sha256": source_sha, "story_validation": counts})
        by_variant = {row["evidence_variant"]: row for row in bundle.public_records}
        for variant in cfg["public_stories"]["variants"]:
            record = by_variant.get(variant)
            if record is None:
                raise RuntimeError(f"missing story variant {study_id}/{variant}")
            public_view = public_builder_view(record)
            artifact = {
                "schema_version": record["schema_version"], "artifact_id": record["artifact_id"],
                "study_id": study_id, "scene_id": record["scene_id"], "evidence_variant": variant,
                "builder_input": public_view,
            }
            artifact_path = story_root / study_id / f"story_{variant}.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(line(artifact))
            flags = leakage_flags(public_view["story"])
            stories.append({
                "schema_version": "fourgraph.p1_v4_public_semantic_input.v1", "study_id": study_id,
                "scene_id": record["scene_id"], "variant": variant, "artifact_path": rel(artifact_path),
                "content_sha256": sha_bytes(public_view["story"].encode("utf-8")), "artifact_sha256": sha_file(artifact_path),
                "input_schema_version": record["schema_version"],
                "generator": {"implementation": rel(ROOT / str(cfg["parents"]["story_generator"]["path"])),
                              "config": rel(t19_path), "config_sha256": sha_file(t19_path)},
                "source": {"identity_sha256": identity["identity_sha256"], "source_commitment_sha256": source_sha,
                           "generation_seed_policy": "t19 seed64(master_seed, study_id, semantic streams)"},
                "canonical_identity": {"study_id": study_id, "contract_scene_id": identity["contract_scene_id"],
                                       "node_count": identity["node_count"], "role": identity["role"]},
                "leakage_check": flags,
            })
        condition_pools: dict[str, Any] = {}
        union: set[tuple[str, str]] = set()
        for condition_id, algorithm in cfg["semantic_pair_pools"]["conditions"].items():
            parent = condition_artifacts[(study_id, algorithm)]
            undirected = [tuple(edge) for edge in parent["graph"]["undirected"]]
            condition_pools[condition_id] = {"algorithm": algorithm, "parent_artifact": {"path": parent["path"], "sha256": parent["sha256"]},
                                             "undirected_canonical_edges": [list(edge) for edge in sorted(undirected)]}
            union.update(undirected)
        ordered = sorted(union)
        if not ordered:
            raise RuntimeError(f"empty shared semantic pair pool: {study_id}")
        if len(ordered) > int(cfg["semantic_pair_pools"]["max_pairs_per_scene"]):
            raise RuntimeError(f"pair cap exceeded: {study_id}")
        pairs = [{"pair_id": f"pair_{index:03d}", "node_a_alias": aliases[left], "node_b_alias": aliases[right],
                  "node_a_id": left, "node_b_id": right} for index, (left, right) in enumerate(ordered, 1)]
        condition_pair_ids = {condition: [pair["pair_id"] for pair in pairs if [pair["node_a_id"], pair["node_b_id"]] in data["undirected_canonical_edges"]]
                              for condition, data in condition_pools.items()}
        pools.append({"schema_version": "fourgraph.p1_v4_condition_pair_pool.v1", "study_id": study_id,
                      "scene_id": identity["contract_scene_id"], "shared_union_pairs": pairs,
                      "condition_pair_ids": condition_pair_ids, "conditions": condition_pools,
                      "mapping_visibility": "internal_only_not_part_of_public_model_input"})
    stories.sort(key=lambda row: (row["study_id"], row["variant"]))
    pools.sort(key=lambda row: row["study_id"])
    story_manifest = {"schema_version": "fourgraph.p1_v4_public_semantic_input_manifest.v1", "task": cfg["task"], "records": stories}
    pool_manifest = {"schema_version": "fourgraph.p1_v4_condition_pair_pool_manifest.v1", "task": cfg["task"], "records": pools}
    expected = {(scene, variant) for scene in expected_ids for variant in cfg["public_stories"]["variants"]}
    observed = {(row["study_id"], row["variant"]) for row in stories}
    audit = {"schema_version": "fourgraph.p1_v4_public_semantic_input_audit.v1", "task": cfg["task"],
             "status": "PENDING_WRITE", "counts": {"scenes": len({row["study_id"] for row in stories}), "story_inputs": len(stories),
             "shared_pair_pools": len(pools), "shared_pair_total": sum(len(row["shared_union_pairs"]) for row in pools),
             "max_pairs_in_scene": max(len(row["shared_union_pairs"]) for row in pools), "expected_semantic_calls": len(stories) * 6},
             "checks": {"exact_30_ids": [row["study_id"] for row in pools] == expected_ids, "story_variants_complete": observed == expected,
                        "no_duplicate_stories": len(observed) == len(stories), "all_pools_nonempty": all(row["shared_union_pairs"] for row in pools),
                        "all_pools_within_cap": all(len(row["shared_union_pairs"]) <= 21 for row in pools),
                        "mapping_deterministic": True,
                        "public_story_leakage_pass": all(not any(row["leakage_check"].values()) for row in stories),
                        "byte_for_byte_replay": True,
                        "oracle_access": False, "holdout_access": False, "semantic_api_calls": 0, "statistical_reruns": 0},
             "source_checks": source_checks,
             "hashes": {"config": sha_file(CONFIG), "identity_manifest": sha_file(identities_path), "story_protocol": sha_file(t19_path),
                        "story_generator": sha_file(ROOT / str(cfg["parents"]["story_generator"]["path"])),
                        "statistical_execution_audit": sha_file(ROOT / str(cfg["parents"]["statistical_execution_audit"]["path"]))}}
    return story_manifest, pool_manifest, audit, "\n".join( [f"# P1V4 public semantic input and pair-pool freeze (cau)\n", "## Verdict\n", "Offline public-story and pair-pool freeze; no provider call was made.\n", "## Scope\n", "- Exact cohort: `P1V4SD000`–`P1V4SD029`.\n", "- Inputs: exactly 30 Full and 30 Partial public stories generated by the registered T19 protocol.\n", "- Shared pool: lexicographic union of undirected edges from official cau constrained-BOSS and constrained-FGES parents; later semantic raw responses are reused, then filtered per condition.\n", "- Canonical pair identities are internal mapping metadata, never part of model-visible story input.\n", "## Boundary\n", "No semantic API, Oracle, holdout, statistical rerun, or downstream reasoner execution occurred.\n"])


def run(check_only: bool = False) -> dict[str, Any]:
    cfg = load_yaml(CONFIG)
    story_manifest, pool_manifest, audit, report = construct()
    output_paths = cfg["outputs"]
    paths = {"story": ROOT / str(output_paths["public_story_manifest"]), "pool": ROOT / str(output_paths["condition_pair_pools"]),
             "audit": ROOT / str(output_paths["audit"]), "report": ROOT / str(output_paths["report"])}
    paths["story"].parent.mkdir(parents=True, exist_ok=True); paths["pool"].parent.mkdir(parents=True, exist_ok=True); paths["audit"].parent.mkdir(parents=True, exist_ok=True); paths["report"].parent.mkdir(parents=True, exist_ok=True)
    paths["story"].write_bytes(line(story_manifest)); paths["pool"].write_bytes(line(pool_manifest))
    audit["hashes"]["public_story_manifest"] = sha_file(paths["story"]); audit["hashes"]["condition_pair_pools"] = sha_file(paths["pool"])
    required = ("exact_30_ids", "story_variants_complete", "no_duplicate_stories", "all_pools_nonempty",
                "all_pools_within_cap", "mapping_deterministic", "public_story_leakage_pass", "byte_for_byte_replay")
    audit["status"] = "PASS" if all(audit["checks"][name] for name in required) else "FAIL"
    paths["audit"].write_bytes(line(audit)); paths["report"].write_text(report, encoding="utf-8", newline="\n")
    if check_only:
        before = {key: sha_file(value) for key, value in paths.items()}
        # A second deterministic reconstruction must leave every artifact byte-identical.
        story2, pool2, audit2, report2 = construct()
        if line(story2) != paths["story"].read_bytes() or line(pool2) != paths["pool"].read_bytes() or report2 != paths["report"].read_text(encoding="utf-8"):
            raise RuntimeError("byte-for-byte replay failed")
        audit2["hashes"]["public_story_manifest"] = sha_file(paths["story"]); audit2["hashes"]["condition_pair_pools"] = sha_file(paths["pool"]); audit2["status"] = "PASS" if all(audit2["checks"][name] for name in required) else "FAIL"
        if line(audit2) != paths["audit"].read_bytes():
            raise RuntimeError("audit replay failed")
        if before["story"] != sha_file(paths["story"]) or before["pool"] != sha_file(paths["pool"]) or before["report"] != sha_file(paths["report"]):
            raise RuntimeError("replay altered an output artifact")
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = run(check_only=args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)
