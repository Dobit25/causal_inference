"""Generate, freeze, or byte-check the fully offline T21 v3-C cohort."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.p1_generation import (  # noqa: E402
    artifact_entry,
    canonical_line,
    edge_count_band,
    npy_bytes,
    sample_observations,
    scene_scm_record,
    standardize,
    task_bundle,
    unresolved_band,
)
from fourgraph.p1_stories import VARIANTS, build_story_bundle, public_builder_view, validate_story_bundle  # noqa: E402
from fourgraph.p1_validation_generation import generate_validation_blueprints  # noqa: E402


CONFIG = ROOT / "configs/t21_v3c_validation_generation.yaml"
MODULE = ROOT / "src/fourgraph/p1_validation_generation.py"
SCRIPT = Path(__file__).resolve()


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _entry(path: Path, payload: bytes | None = None) -> dict[str, Any]:
    body = path.read_bytes() if payload is None else payload
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": len(body), "sha256": sha256_hex(body)}


def _target_hashes(bundle: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    return {
        str(row["task_id"]): (
            sha256_hex(canonical_json_bytes(row["expected"])),
            sha256_hex(canonical_json_bytes(row)),
        )
        for row in bundle["tasks"]
    }


def _story_config(config: Mapping[str, Any]) -> dict[str, Any]:
    stories = config["semantic_stories"]
    return {
        "randomness": {"master_seed": config["randomness"]["master_seed"]},
        "aliases": {"lexicon": stories["aliases"]["lexicon"]},
        "stories": {
            "directional_template": stories["directional_template"],
            "symmetric_template": stories["symmetric_template"],
        },
    }


def _validate_config(config: Mapping[str, Any]) -> None:
    if config["schema_version"] != "fourgraph.t21_v3c_validation_generation.v1":
        raise RuntimeError("T21 v3-C config schema drift")
    if np.__version__ != str(config["randomness"]["numpy_version"]):
        raise RuntimeError(f"NumPy drift: {np.__version__}")
    parent = _json(ROOT / str(config["parent_v3b_audit"]))
    verdict = parent["verdict"]
    if not verdict["t21_v3b_complete"] or not verdict["t21_v3c_validation_generation_authorized"]:
        raise RuntimeError("T21 v3-B does not authorize v3-C")
    if verdict["live_api_calls_authorized"] or verdict["holdout_accessed"]:
        raise RuntimeError("T21 v3-B boundary drift")
    protocol = _yaml(ROOT / str(config["parent_protocol"]))
    registered = protocol["cohorts"]["threshold_validation"]
    expected = {
        "count": config["identifiers"]["count"],
        "master_seed": config["randomness"]["master_seed"],
        "node_count_allocation": list(config["graph_generation"]["node_count_allocation"].values()),
        "primary_motif_allocation": config["graph_generation"]["primary_motif_allocation"],
        "noise_family_allocation": {
            "laplace": config["scm"]["noise_family_allocation"]["laplace"],
            "logistic": config["scm"]["noise_family_allocation"]["logistic"],
            "student_t_5": config["scm"]["noise_family_allocation"]["student_t_df5"],
        },
        "observations_per_scene": config["observations"]["sample_size"],
        "story_variants": config["semantic_stories"]["variants"],
        "tasks_per_scene": config["tasks"]["tasks_per_scene"],
    }
    for key, value in expected.items():
        if registered[key] != value:
            raise RuntimeError(f"T21 v3-C protocol allocation drift: {key}")
    registered_strata = registered["query_strata_allocation"]
    mapped = {
        "valid_empty": config["tasks"]["query_stratum_allocation"]["valid_empty"],
        "one_nonempty_minimal": config["tasks"]["query_stratum_allocation"]["one_minimal_nonempty"],
        "multiple_minimal": config["tasks"]["query_stratum_allocation"]["multiple_minimal"],
        "no_valid_adjustment": config["tasks"]["query_stratum_allocation"]["no_valid_adjustment_set"],
    }
    if registered_strata != mapped:
        raise RuntimeError("T21 v3-C query-stratum mapping drift")
    if sum(config["graph_generation"]["node_count_allocation"].values()) != 20:
        raise RuntimeError("Node allocation does not cover 20 scenes")
    if sum(config["graph_generation"]["primary_motif_allocation"].values()) != 20:
        raise RuntimeError("Motif allocation does not cover 20 scenes")
    if sum(config["scm"]["noise_family_allocation"].values()) != 20:
        raise RuntimeError("Noise allocation does not cover 20 scenes")
    if sum(config["tasks"]["query_stratum_allocation"].values()) != 20:
        raise RuntimeError("Query allocation does not cover 20 scenes")
    boundary = config["execution_boundary"]
    forbidden = (
        boundary["api_calls"], boundary["provider_sdk_imports"], boundary["semantic_model_execution"],
        boundary["SCD_execution"], boundary["H1_H2_execution"], boundary["reasoner_execution"],
        boundary["threshold_selection"], boundary["existing_development_scene_artifacts_accessed"],
        boundary["existing_holdout_scene_artifacts_accessed"],
    )
    if any(forbidden):
        raise RuntimeError("T21 v3-C execution boundary drift")
    dependencies = [ROOT / str(item) for item in config["dependencies"]]
    if len(dependencies) != len(set(dependencies)) or any(not path.is_file() for path in dependencies):
        raise RuntimeError("T21 v3-C dependency list missing or duplicated")
    if any("data/generated" in path.as_posix() or "results/raw" in path.as_posix() for path in dependencies):
        raise RuntimeError("T21 v3-C may not depend on existing raw experiment artifacts")


def _distribution(values: list[Any]) -> dict[str, int]:
    return dict(sorted(Counter(map(str, values)).items()))


def _report(audit: Mapping[str, Any]) -> bytes:
    counts = audit["counts"]
    lines = [
        "# T21 v3-C — Frozen validation SCM cohort", "",
        "V3-C đã sinh và đóng băng một cohort validation mới, độc lập với 20 development và 80 holdout scenes hiện hữu.", "",
        f"- SCMs: {counts['scenes']}/20, IDs `P1V000–P1V019`.",
        f"- Observational datasets: {counts['observation_datasets']} raw + standardized pairs at N=2000.",
        f"- Tasks: {counts['tasks']}/100; production/reference solver agreements {counts['task_solver_agreements']}/100.",
        f"- Semantic story stimuli: {counts['stories']}/60 across full/partial/ambiguous; generated deterministically, not by an LLM.",
        f"- Oracle CPDAG unresolved-edge minimum: {counts['minimum_oracle_cpdag_unresolved_edges']}.", "",
        "SCM truth, expected answers, alias mappings and story truth remain in the ignored generated tree. Versioned manifests contain exact IDs, queries, hashes and non-semantic inventory metadata.", "",
        "V3-C made zero API calls, did not run BOSS/SCD/H1/H2/reasoner, did not select a threshold, and accessed no existing development or holdout scene artifact. Only T21 v3-D validation semantic calls and the preregistered twenty-candidate gate are authorized next; the 80 final holdout scenes remain sealed.", "",
    ]
    return "\n".join(lines).encode("utf-8")


def build() -> tuple[dict[Path, bytes], dict[Path, bytes], dict[str, Any]]:
    config = _yaml(CONFIG)
    _validate_config(config)
    blueprints, agreements = generate_validation_blueprints(config)
    gates = config["gates"]
    if len(blueprints) != gates["scenes"] or agreements != gates["production_reference_task_agreements"]:
        raise RuntimeError("Validation blueprint/task agreement gate failed")
    raw_root = ROOT / str(config["artifacts"]["raw_root"])
    raw: dict[Path, bytes] = {}
    inventory: list[dict[str, Any]] = []
    tasks_public: list[dict[str, Any]] = []
    stories_public: list[dict[str, Any]] = []
    aliases_public: list[dict[str, Any]] = []
    story_config = _story_config(config)
    edge_ranges = {
        int(key): tuple(map(int, value))
        for key, value in config["graph_generation"]["edge_count_range_by_nodes"].items()
    }
    max_mean_error = 0.0
    max_sd_error = 0.0
    story_directional = Counter()
    for scene in blueprints:
        scene_dir = raw_root / scene.study_id
        scm = scene_scm_record(scene)
        scm_payload = canonical_line(scm)
        bundle, scene_agreements = task_bundle(scene)
        if scene_agreements != 5:
            raise RuntimeError(f"Task solver disagreement: {scene.study_id}")
        tasks_payload = canonical_line(bundle)
        values = sample_observations(scene, int(config["randomness"]["master_seed"]), int(config["observations"]["sample_size"]))
        standardized = standardize(values)
        max_mean_error = max(max_mean_error, float(np.max(np.abs(standardized.mean(axis=0)))))
        max_sd_error = max(max_sd_error, float(np.max(np.abs(standardized.std(axis=0) - 1.0))))
        raw_payload = npy_bytes(values)
        std_payload = npy_bytes(standardized)
        raw[scene_dir / "scm.json"] = scm_payload
        raw[scene_dir / "tasks_grading.json"] = tasks_payload
        raw[scene_dir / "observations_raw_n2000.npy"] = raw_payload
        raw[scene_dir / "observations_standardized_n2000.npy"] = std_payload

        story_bundle = build_story_bundle(scm, story_config)
        story_counts = validate_story_bundle(story_bundle, story_config)
        alias_record = {
            "schema_version": "fourgraph.p1_alias_map.v1", "study_id": scene.study_id,
            "scene_id": scene.contract_scene_id, "adapter_only_not_model_input": True,
            "mapping": [{"canonical_id": node, "public_alias": alias} for node, alias in story_bundle.alias_map],
        }
        alias_payload = canonical_line(alias_record)
        raw[scene_dir / "alias_map.json"] = alias_payload
        raw[scene_dir / "story_truth.json"] = canonical_line(story_bundle.truth_record)
        aliases_public.append({
            "schema_version": "fourgraph.t21_v3c_alias_manifest.v1", "study_id": scene.study_id,
            "scene_id": scene.contract_scene_id, "mapping_entries": scene.node_count,
            "mapping_sha256": sha256_hex(alias_payload), "public_aliases_persisted": False,
            "model_visible": False,
        })
        for record in story_bundle.public_records:
            variant = str(record["evidence_variant"])
            payload = canonical_line(record)
            path = scene_dir / f"story_{variant}.json"
            raw[path] = payload
            story_directional[variant] += story_counts[variant]
            stories_public.append({
                "schema_version": "fourgraph.t21_v3c_story_manifest.v1",
                "artifact_id": record["artifact_id"], "study_id": scene.study_id,
                "scene_id": scene.contract_scene_id, "variant": variant,
                "artifact_path": path.relative_to(ROOT).as_posix(), "artifact_bytes": len(payload),
                "artifact_sha256": sha256_hex(payload),
                "builder_view_sha256": sha256_hex(canonical_json_bytes(public_builder_view(record))),
                "directional_claim_count": story_counts[variant], "gold_graph_persisted": False,
                "story_text_persisted": False,
            })

        targets = _target_hashes(bundle)
        for row in bundle["tasks"]:
            target_hash, record_hash = targets[row["task_id"]]
            tasks_public.append({
                "schema_version": "fourgraph.t21_v3c_task_manifest.v1",
                "study_id": scene.study_id, "scene_id": scene.contract_scene_id,
                "query_id": row["query_id"], "task_id": row["task_id"], "query": row["query"],
                "expected_target_sha256": target_hash, "grading_record_sha256": record_hash,
                "gold_answer_persisted": False, "solver_agreement": True,
            })
        scene_files = [
            artifact_entry(path.relative_to(ROOT).as_posix(), payload)
            for path, payload in sorted(raw.items(), key=lambda item: item[0].as_posix())
            if path.parent == scene_dir
        ]
        inventory.append({
            "schema_version": "fourgraph.t21_v3c_validation_inventory.v1",
            "study_id": scene.study_id, "scene_id": scene.contract_scene_id,
            "cohort_role": "threshold_validation_only", "node_count": scene.node_count,
            "edge_count": len(scene.dag.directed),
            "edge_count_band": edge_count_band(scene.node_count, len(scene.dag.directed), edge_ranges),
            "variable_types": ["continuous"], "observed_node_count": scene.node_count,
            "latent_node_count": 0, "connected": True,
            "assigned_primary_motif": scene.assigned_primary_motif,
            "verified_motifs": list(scene.motifs), "exogenous_noise_family": scene.noise_family,
            "generation_attempt": scene.generation_attempt,
            "oracle_cpdag_directed_edges": len(scene.oracle_cpdag.directed),
            "oracle_cpdag_unresolved_edges": len(scene.oracle_cpdag.undirected),
            "oracle_cpdag_unresolved_edge_band": unresolved_band(len(scene.oracle_cpdag.undirected)),
            "query_target_stratum": scene.query_target_stratum,
            "treatment": scene.query_treatment, "outcome": scene.query_outcome,
            "candidate_count": scene.node_count - 2, "task_count": 5,
            "observation_sample_sizes": [2000],
            "component_seed_commitment_sha256": sha256_hex(canonical_json_bytes(dict(scene.component_seeds))),
            "artifacts": scene_files,
        })

    if max_mean_error > float(gates["standardized_mean_absolute_max"]):
        raise RuntimeError("Standardized mean gate failed")
    if max_sd_error > float(gates["standardized_sd_absolute_error_max"]):
        raise RuntimeError("Standardized SD gate failed")
    ids = [scene.study_id for scene in blueprints]
    scene_ids = [scene.contract_scene_id for scene in blueprints]
    if ids != [f"P1V{index:03d}" for index in range(20)] or scene_ids != [f"scene_{110000 + index:06d}" for index in range(20)]:
        raise RuntimeError("Validation namespace drift")
    minimum_unresolved = min(len(scene.oracle_cpdag.undirected) for scene in blueprints)
    if minimum_unresolved < int(gates["oracle_cpdag_minimum_unresolved_edges_per_scene"]):
        raise RuntimeError("Oracle CPDAG uncertainty gate failed")

    inventory.sort(key=lambda row: row["study_id"])
    tasks_public.sort(key=lambda row: (row["study_id"], row["task_id"]))
    stories_public.sort(key=lambda row: (row["study_id"], VARIANTS.index(row["variant"])))
    aliases_public.sort(key=lambda row: row["study_id"])
    cohort = {
        "schema_version": "fourgraph.t21_v3c_validation_cohort.v1", "role": "threshold_validation_only",
        "master_seed": config["randomness"]["master_seed"], "study_ids": ids, "scene_ids": scene_ids,
        "study_to_scene": [{"study_id": scene.study_id, "scene_id": scene.contract_scene_id} for scene in blueprints],
        "existing_development_overlap": [], "existing_holdout_overlap": [],
        "threshold_selection_allowed_only_at_t21_v3d": True,
        "final_holdout_eligible": False,
    }
    paths = config["artifacts"]
    versioned: dict[Path, bytes] = {
        ROOT / str(paths["inventory"]): b"".join(canonical_line(row) for row in inventory),
        ROOT / str(paths["cohort_freeze"]): canonical_json_bytes(cohort),
        ROOT / str(paths["task_manifest"]): b"".join(canonical_line(row) for row in tasks_public),
        ROOT / str(paths["story_manifest"]): b"".join(canonical_line(row) for row in stories_public),
        ROOT / str(paths["alias_manifest"]): b"".join(canonical_line(row) for row in aliases_public),
    }
    raw_entries = [_entry(path, payload) for path, payload in sorted(raw.items(), key=lambda item: item[0].as_posix())]
    raw_tree_hash = sha256_hex(canonical_json_bytes(raw_entries))
    counts = {
        "scenes": len(blueprints), "observation_datasets": len(blueprints),
        "tasks": len(tasks_public), "task_solver_agreements": agreements,
        "stories": len(stories_public), "alias_maps": len(aliases_public),
        "minimum_oracle_cpdag_unresolved_edges": minimum_unresolved,
        "full_directional_claims": story_directional["full"],
        "partial_directional_claims": story_directional["partial"],
        "ambiguous_directional_claims": story_directional["ambiguous"],
    }
    audit: dict[str, Any] = {
        "schema_version": "fourgraph.t21_v3c_validation_generation_audit.v1", "task": "T21 Amendment v3-C",
        "experiment_id": config["experiment_id"],
        "dependencies": [_entry(path) for path in [CONFIG, MODULE, SCRIPT, *(ROOT / str(item) for item in config["dependencies"])]],
        "outputs": [],
        "raw_artifact_tree": {"root": raw_root.relative_to(ROOT).as_posix(), "file_count": len(raw_entries), "bytes": sum(x["bytes"] for x in raw_entries), "sha256": raw_tree_hash},
        "counts": counts,
        "distributions": {
            "node_count": _distribution([scene.node_count for scene in blueprints]),
            "assigned_primary_motif": _distribution([scene.assigned_primary_motif for scene in blueprints]),
            "noise_family": _distribution([scene.noise_family for scene in blueprints]),
            "query_target_stratum": _distribution([scene.query_target_stratum for scene in blueprints]),
        },
        "numerical_audit": {"maximum_standardized_absolute_mean": max_mean_error, "maximum_standardized_sd_error": max_sd_error},
        "boundary": config["execution_boundary"],
        "verdict": {
            "t21_v3c_complete": True, "validation_cohort_frozen": True,
            "validation_scenes_generated": 20, "task_solver_agreement_passed": True,
            "story_truth_audit_passed": True, "deterministic_replay_required": True,
            "api_calls": 0, "semantic_model_executed": False, "SCD_H1_H2_reasoner_executed": False,
            "existing_development_artifacts_accessed": 0, "existing_holdout_artifacts_accessed": 0,
            "threshold_selected": False, "t21_v3d_authorized": True,
            "final_holdout_access_authorized": False,
        },
    }
    report = _report(audit)
    report_path = ROOT / str(paths["report"])
    audit["outputs"] = [_entry(path, payload) for path, payload in sorted({**versioned, report_path: report}.items(), key=lambda item: item[0].as_posix())]
    versioned[report_path] = report
    versioned[ROOT / str(paths["audit"])] = canonical_json_bytes(audit)
    return versioned, raw, audit


def _materialize(files: Mapping[Path, bytes]) -> None:
    for path, payload in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _check_tree(files: Mapping[Path, bytes], root: Path) -> None:
    expected = set(files)
    actual = {path for path in root.rglob("*") if path.is_file()} if root.is_dir() else set()
    if actual != expected:
        raise RuntimeError(f"Raw tree path drift: missing={len(expected-actual)} extra={len(actual-expected)}")
    for path, payload in files.items():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Byte drift: {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    versioned, raw, audit = build()
    config = _yaml(CONFIG)
    raw_root = ROOT / str(config["artifacts"]["raw_root"])
    if args.check:
        _check_tree(raw, raw_root)
        for path, payload in versioned.items():
            if not path.is_file() or path.read_bytes() != payload:
                raise SystemExit(f"T21 v3-C byte drift: {path.relative_to(ROOT)}")
        print(json.dumps({"check": "passed", "scenes": 20, "api_calls": 0, "holdout_accessed": False}))
    else:
        _materialize(raw)
        _materialize(versioned)
        print(json.dumps({"generated_scenes": audit["counts"]["scenes"], "raw_files": audit["raw_artifact_tree"]["file_count"], "api_calls": 0, "holdout_accessed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
