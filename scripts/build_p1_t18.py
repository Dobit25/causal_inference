"""Generate or byte-check the offline T18 fresh-SCM artifact set."""

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
    deterministic_split,
    edge_count_band,
    generate_blueprints,
    npy_bytes,
    sample_observations,
    scene_scm_record,
    stable_rank,
    standardize,
    task_bundle,
    unresolved_band,
)


CONFIG_PATH = ROOT / "configs/t18_p1_generation.yaml"
SCHEMA_PATH = ROOT / "schemas/p1_t18_generation_v1.schema.json"
MODULE_PATH = ROOT / "src/fourgraph/p1_generation.py"
SCRIPT_PATH = Path(__file__).resolve()
INVENTORY_PATH = ROOT / "data/manifests/t18_p1_scene_inventory.jsonl"
SPLIT_PATH = ROOT / "data/manifests/t18_p1_frozen_split.json"
TASK_PATH = ROOT / "data/manifests/t18_p1_task_manifest.jsonl"
AUDIT_PATH = ROOT / "data/manifests/t18_p1_generation_audit.json"
REPORT_PATH = ROOT / "reports/t18_p1_generation.md"


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def path_entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_hex(path.read_bytes()),
    }


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    if config["schema_version"] != "fourgraph.p1_t18_generation.v1":
        raise RuntimeError("T18 config schema drift")
    if np.__version__ != str(config["randomness"]["numpy_version"]):
        raise RuntimeError(f"NumPy drift: {np.__version__}")
    t17 = json_object(ROOT / str(config["parent_freeze"]))
    if not t17["verdict"]["t17_complete"] or not t17["verdict"]["t18_generator_inventory_authorized"]:
        raise RuntimeError("T17 does not authorize T18")
    if t17["verdict"]["live_model_calls_authorized"] or t17["verdict"]["H2_implementation_authorized"]:
        raise RuntimeError("T17 execution boundary drift")
    parent = ROOT / str(config["parent_protocol"])
    if sha256_hex(parent.read_bytes()) != t17["protocol"]["sha256"]:
        raise RuntimeError("T17 parent protocol hash drift")
    protocol = load_yaml(parent)
    if config["randomness"]["master_seed"] != protocol["experiment"]["master_seed"]:
        raise RuntimeError("Master seed drift")
    if config["split"]["seed"] != protocol["generation"]["split"]["seed"]:
        raise RuntimeError("Split seed drift")
    if sum(config["graph_generation"]["node_count_allocation"].values()) != 100:
        raise RuntimeError("Node allocation drift")
    if sum(config["graph_generation"]["primary_motif_allocation"].values()) != 100:
        raise RuntimeError("Motif allocation drift")
    if sum(config["scm"]["noise_family_allocation"].values()) != 100:
        raise RuntimeError("Noise allocation drift")
    if sum(config["tasks"]["query_stratum_allocation"].values()) != 100:
        raise RuntimeError("Query allocation drift")
    boundary = config["access_boundary"]
    if boundary["api_calls"] or boundary["H2_implementation_authorized"]:
        raise RuntimeError("T18 cannot authorize API/H2")
    if boundary["statistical_or_semantic_method_execution_authorized"]:
        raise RuntimeError("T18 cannot execute study methods")
    dependency_paths = [ROOT / str(path) for path in config["dependencies"]]
    if len(dependency_paths) != len(set(dependency_paths)) or any(
        not path.is_file() for path in dependency_paths
    ):
        raise RuntimeError("T18 dependency list is missing or duplicated")
    return protocol


def _scene_metadata(blueprint: Any, edge_ranges: Mapping[int, tuple[int, int]]) -> dict[str, Any]:
    return {
        "node_count": blueprint.node_count,
        "edge_count_band": edge_count_band(
            blueprint.node_count, len(blueprint.dag.directed), edge_ranges
        ),
        "assigned_primary_motif": blueprint.assigned_primary_motif,
        "oracle_cpdag_unresolved_edge_band": unresolved_band(
            len(blueprint.oracle_cpdag.undirected)
        ),
        "query_target_stratum": blueprint.query_target_stratum,
        "exogenous_noise_family": blueprint.noise_family,
    }


def _select_sensitivity(
    development: tuple[str, ...], holdout: tuple[str, ...], seed: int
) -> set[str]:
    dev = sorted(development, key=lambda scene: stable_rank(seed, "sensitivity", "development", scene))[:4]
    held = sorted(holdout, key=lambda scene: stable_rank(seed, "sensitivity", "holdout", scene))[:16]
    return set(dev + held)


def _target_hashes(bundle: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    result = {}
    for row in bundle["tasks"]:
        target_hash = sha256_hex(canonical_json_bytes(row["expected"]))
        record_hash = sha256_hex(canonical_json_bytes(row))
        result[str(row["task_id"])] = (target_hash, record_hash)
    return result


def _distribution(values: list[Any]) -> dict[str, int]:
    return dict(sorted(Counter(map(str, values)).items()))


def _report(
    development: tuple[str, ...],
    holdout: tuple[str, ...],
    sensitivity: set[str],
    split_audit: Mapping[str, Any],
    raw_bytes: int,
    generation_attempts: list[int],
) -> bytes:
    dev_text = ", ".join(f"`{scene}`" for scene in development)
    lines = [
        "# T18 — Fresh-SCM generator, inventory và frozen P1 split",
        "",
        "## Kết quả",
        "",
        "T18 đã sinh deterministically 100 linear non-Gaussian SCMs mà không gọi API, không chạy SCD/LLM/Hybrid và không chấm holdout. Mỗi scene có đúng năm task; production solver và independent active-path solver khớp 500/500 targets.",
        "",
        "- 100 scenes: 20 development / 80 holdout.",
        "- 5–7 observed continuous nodes; connected DAG; không latent node.",
        "- Mỗi Oracle CPDAG có ít nhất hai unresolved edges.",
        "- Primary observations: `N=2000` trên 100/100 scenes.",
        "- Nested `N=500/10000`: 20 scenes, gồm 4 development và 16 holdout.",
        f"- Raw ignored artifact tree: {raw_bytes:,} bytes.",
        f"- Generation attempts: tổng {sum(generation_attempts)}, median {float(np.median(generation_attempts)):.1f}, tối đa {max(generation_attempts)} / 10.000.",
        f"- Split maximum rounded marginal deviation: {split_audit['maximum_rounded_marginal_count_deviation']} scene; gate cho phép tối đa 2.",
        "",
        "## Exact development IDs",
        "",
        dev_text,
        "",
        "80 ID còn lại được đóng băng là holdout trong `data/manifests/t18_p1_frozen_split.json`. Mapping `P1Sxxx` sang `scene_100xxx` là một-một để tương thích graph contract T06.",
        "",
        "## Artifact và leakage boundary",
        "",
        "SCM equations, Oracle DAG/CPDAG, component seeds và expected answers nằm dưới `data/generated/p1_hybrid_v1/t18/`, bị Git ignore. Inventory được version hóa chỉ chứa metadata và hashes; task manifest chứa query cùng target commitment hash nhưng không chứa gold answer. Loader ở các bước sau vẫn phải enforce evidence boundary, vì hash/inventory không tự thay thế access control.",
        "",
        "T18 được phép dùng Oracle-only structural/task properties để tạo split trước method development. Không output nào của BOSS, DirectLiNGAM, LLM, H1, H2 hoặc reasoner được tạo hay dùng khi chọn split.",
        "",
        "## Kết luận và quyền tiếp theo",
        "",
        "T18 đạt mọi generation, nesting, solver-agreement, balance và byte-replay gate. Chỉ T19 deterministic semantic-story variants/manual audit được cấp quyền tiếp theo. Live model calls, H2 implementation/execution và P1 holdout evaluation vẫn chưa được cấp quyền.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build() -> tuple[dict[Path, bytes], dict[Path, bytes], dict[str, Any]]:
    config = load_yaml(CONFIG_PATH)
    validate_config(config)
    blueprints, initial_agreements = generate_blueprints(config)
    if len(blueprints) != 100 or initial_agreements != 500:
        raise RuntimeError("Blueprint/solver count gate failed")
    edge_ranges = {
        int(key): tuple(map(int, value))
        for key, value in config["graph_generation"]["edge_count_range_by_nodes"].items()
    }
    metadata = {
        scene.study_id: _scene_metadata(scene, edge_ranges) for scene in blueprints
    }
    development, holdout, split_audit = deterministic_split(metadata, config)
    max_allowed = int(config["split"]["maximum_allowed_rounded_marginal_count_deviation"])
    if split_audit["maximum_rounded_marginal_count_deviation"] > max_allowed:
        raise RuntimeError("Stratification balance gate failed")
    sensitivity = _select_sensitivity(development, holdout, int(config["split"]["seed"]))
    if len(sensitivity & set(development)) != 4 or len(sensitivity & set(holdout)) != 16:
        raise RuntimeError("Sensitivity split gate failed")

    raw_root = ROOT / str(config["artifacts"]["raw_root"])
    raw_files: dict[Path, bytes] = {}
    inventory_rows: list[dict[str, Any]] = []
    public_task_rows: list[dict[str, Any]] = []
    agreements = 0
    max_mean_error = 0.0
    max_sd_error = 0.0
    nested_prefix_transitions_checked = 0
    standardized_arrays_checked = 0
    for scene in blueprints:
        role = "development" if scene.study_id in development else "holdout"
        is_sensitivity = scene.study_id in sensitivity
        scene_dir = raw_root / scene.study_id
        scm_payload = canonical_line(scene_scm_record(scene))
        bundle, scene_agreements = task_bundle(scene)
        agreements += scene_agreements
        task_payload = canonical_line(bundle)
        raw_files[scene_dir / "scm.json"] = scm_payload
        raw_files[scene_dir / "tasks_grading.json"] = task_payload
        target_hashes = _target_hashes(bundle)

        maximum_n = 10000 if is_sensitivity else 2000
        maximum = sample_observations(scene, int(config["randomness"]["master_seed"]), maximum_n)
        sample_sizes = [500, 2000, 10000] if is_sensitivity else [2000]
        data_entries = []
        prior_raw: np.ndarray | None = None
        for sample_size in sample_sizes:
            raw = np.asarray(maximum[:sample_size], dtype="<f8")
            if prior_raw is not None and not np.array_equal(raw[: len(prior_raw)], prior_raw):
                raise RuntimeError(f"Nested-prefix failure for {scene.study_id}")
            if prior_raw is not None:
                nested_prefix_transitions_checked += 1
            standardized = standardize(raw)
            standardized_arrays_checked += 1
            max_mean_error = max(max_mean_error, float(np.max(np.abs(standardized.mean(axis=0)))))
            max_sd_error = max(max_sd_error, float(np.max(np.abs(standardized.std(axis=0) - 1.0))))
            raw_path = scene_dir / f"observations_raw_n{sample_size}.npy"
            std_path = scene_dir / f"observations_standardized_n{sample_size}.npy"
            raw_files[raw_path] = npy_bytes(raw)
            raw_files[std_path] = npy_bytes(standardized)
            data_entries.extend(
                [
                    artifact_entry(raw_path.relative_to(ROOT).as_posix(), raw_files[raw_path]),
                    artifact_entry(std_path.relative_to(ROOT).as_posix(), raw_files[std_path]),
                ]
            )
            prior_raw = raw

        file_entries = [
            artifact_entry((scene_dir / "scm.json").relative_to(ROOT).as_posix(), scm_payload),
            artifact_entry((scene_dir / "tasks_grading.json").relative_to(ROOT).as_posix(), task_payload),
            *data_entries,
        ]
        seed_commitment = sha256_hex(canonical_json_bytes(dict(scene.component_seeds)))
        inventory_rows.append(
            {
                "schema_version": "fourgraph.p1_scene_inventory.v1",
                "study_id": scene.study_id,
                "scene_id": scene.contract_scene_id,
                "split": role,
                "sensitivity_scene": is_sensitivity,
                "node_count": scene.node_count,
                "edge_count": len(scene.dag.directed),
                "edge_count_band": metadata[scene.study_id]["edge_count_band"],
                "variable_types": ["continuous"],
                "observed_node_count": scene.node_count,
                "latent_node_count": 0,
                "connected": True,
                "assigned_primary_motif": scene.assigned_primary_motif,
                "verified_motifs": list(scene.motifs),
                "exogenous_noise_family": scene.noise_family,
                "generation_attempt": scene.generation_attempt,
                "oracle_cpdag_directed_edges": len(scene.oracle_cpdag.directed),
                "oracle_cpdag_unresolved_edges": len(scene.oracle_cpdag.undirected),
                "oracle_cpdag_unresolved_edge_band": metadata[scene.study_id]["oracle_cpdag_unresolved_edge_band"],
                "query_target_stratum": scene.query_target_stratum,
                "treatment": scene.query_treatment,
                "outcome": scene.query_outcome,
                "candidate_count": scene.node_count - 2,
                "task_count": 5,
                "observation_sample_sizes": sample_sizes,
                "component_seed_commitment_sha256": seed_commitment,
                "artifacts": sorted(file_entries, key=lambda item: item["path"]),
            }
        )
        for task_row in bundle["tasks"]:
            target_hash, grading_hash = target_hashes[str(task_row["task_id"])]
            public_task_rows.append(
                {
                    "schema_version": "fourgraph.p1_task_manifest.v1",
                    "study_id": scene.study_id,
                    "scene_id": scene.contract_scene_id,
                    "split": role,
                    "query_target_stratum": scene.query_target_stratum,
                    "query_id": task_row["query_id"],
                    "task_id": task_row["task_id"],
                    "query": task_row["query"],
                    "query_sha256": sha256_hex(canonical_json_bytes(task_row["query"])),
                    "expected_target_sha256": target_hash,
                    "grading_record_sha256": grading_hash,
                    "gold_answer_in_versioned_manifest": False,
                }
            )

    if agreements != 500:
        raise RuntimeError("Final solver agreement is not 500/500")
    inventory_rows.sort(key=lambda row: row["study_id"])
    public_task_rows.sort(key=lambda row: (row["study_id"], config["tasks"]["task_ids"].index(row["task_id"])))
    inventory_bytes = b"".join(canonical_line(row) for row in inventory_rows)
    task_bytes = b"".join(canonical_line(row) for row in public_task_rows)
    mappings = [
        {"study_id": row["study_id"], "scene_id": row["scene_id"]}
        for row in inventory_rows
    ]
    split_record = {
        "schema_version": "fourgraph.p1_t18_frozen_split.v1",
        "experiment_id": config["experiment_id"],
        "unit": "study_id",
        "seed": config["split"]["seed"],
        "development_ids": list(development),
        "holdout_ids": list(holdout),
        "development_contract_scene_ids": [f"scene_{100000 + int(scene[-3:]):06d}" for scene in development],
        "holdout_contract_scene_ids": [f"scene_{100000 + int(scene[-3:]):06d}" for scene in holdout],
        "study_to_contract_scene_id": mappings,
        "sensitivity_development_ids": sorted(sensitivity & set(development)),
        "sensitivity_holdout_ids": sorted(sensitivity & set(holdout)),
        "stratification": split_audit,
        "exact_ids_frozen": True,
        "method_outputs_used": [],
    }
    split_bytes = canonical_line(split_record)
    raw_entries = [
        artifact_entry(path.relative_to(ROOT).as_posix(), payload)
        for path, payload in sorted(raw_files.items(), key=lambda item: item[0].as_posix())
    ]
    raw_tree_hash = sha256_hex(canonical_json_bytes(raw_entries))
    raw_byte_count = sum(item["bytes"] for item in raw_entries)
    report_bytes = _report(
        development,
        holdout,
        sensitivity,
        split_audit,
        raw_byte_count,
        [scene.generation_attempt for scene in blueprints],
    )
    preliminary_outputs = {
        INVENTORY_PATH: inventory_bytes,
        SPLIT_PATH: split_bytes,
        TASK_PATH: task_bytes,
        REPORT_PATH: report_bytes,
    }
    dependencies = [CONFIG_PATH, SCHEMA_PATH, MODULE_PATH, SCRIPT_PATH]
    dependencies.extend(ROOT / str(path) for path in config["dependencies"])
    dependencies = list(dict.fromkeys(dependencies))
    audit = {
        "schema_version": "fourgraph.p1_t18_generation_audit.v1",
        "task": "T18",
        "experiment_id": config["experiment_id"],
        "dependencies": [path_entry(path) for path in dependencies],
        "outputs": [
            artifact_entry(path.relative_to(ROOT).as_posix(), payload)
            for path, payload in sorted(preliminary_outputs.items(), key=lambda item: item[0].as_posix())
        ],
        "raw_artifact_tree": {
            "root": Path(config["artifacts"]["raw_root"]).as_posix(),
            "file_count": len(raw_entries),
            "bytes": raw_byte_count,
            "sha256": raw_tree_hash,
        },
        "counts": {
            "scenes": 100,
            "development_scenes": len(development),
            "holdout_scenes": len(holdout),
            "tasks": len(public_task_rows),
            "tasks_per_scene": 5,
            "production_independent_solver_agreements": agreements,
            "primary_n_scenes": 100,
            "sensitivity_n500_n10000_scenes": len(sensitivity),
            "sensitivity_development_scenes": len(sensitivity & set(development)),
            "sensitivity_holdout_scenes": len(sensitivity & set(holdout)),
        },
        "distributions": {
            "node_count": _distribution([scene.node_count for scene in blueprints]),
            "assigned_primary_motif": _distribution([scene.assigned_primary_motif for scene in blueprints]),
            "noise_family": _distribution([scene.noise_family for scene in blueprints]),
            "query_target_stratum": _distribution([scene.query_target_stratum for scene in blueprints]),
            "edge_count_band": _distribution([metadata[scene.study_id]["edge_count_band"] for scene in blueprints]),
            "oracle_cpdag_unresolved_edge_band": _distribution([metadata[scene.study_id]["oracle_cpdag_unresolved_edge_band"] for scene in blueprints]),
        },
        "generation_diagnostics": {
            "total_candidate_attempts": sum(scene.generation_attempt for scene in blueprints),
            "maximum_candidate_attempts": max(scene.generation_attempt for scene in blueprints),
            "minimum_oracle_cpdag_unresolved_edges": min(len(scene.oracle_cpdag.undirected) for scene in blueprints),
            "nested_prefix_transitions_checked": nested_prefix_transitions_checked,
            "standardized_arrays_checked": standardized_arrays_checked,
            "maximum_standardized_absolute_column_mean": max_mean_error,
            "maximum_standardized_absolute_population_sd_error": max_sd_error,
        },
        "split_balance": split_audit,
        "evidence_boundary": {
            "api_calls": 0,
            "provider_SDK_imported_or_called": False,
            "H2_implemented_or_executed": False,
            "SCD_or_semantic_method_executed": False,
            "holdout_generated": True,
            "holdout_oracle_inventory_used_only_for_prespecified_stratification": True,
            "holdout_method_results_accessed": False,
            "holdout_downstream_scored": False,
            "gold_answers_in_versioned_task_manifest": False,
        },
        "verdict": {
            "t18_complete": True,
            "generator_reproducible": True,
            "all_100_scenes_eligible": True,
            "solver_agreement_500_of_500": True,
            "exact_split_frozen": True,
            "t19_story_generation_authorized": True,
            "live_model_calls_authorized": False,
            "H2_implementation_authorized": False,
            "p1_holdout_evaluation_authorized": False,
        },
    }
    versioned = {**preliminary_outputs, AUDIT_PATH: canonical_line(audit)}
    summary = {
        "t18_complete": True,
        "scenes": 100,
        "tasks": agreements,
        "development": len(development),
        "holdout": len(holdout),
        "raw_files": len(raw_entries),
        "raw_tree_sha256": raw_tree_hash,
        "t19_authorized": True,
    }
    return versioned, raw_files, summary


def _compare(path: Path, expected: bytes) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing artifact: {path.relative_to(ROOT)}")
    actual = path.read_bytes()
    if actual != expected:
        raise RuntimeError(
            f"Byte drift: {path.relative_to(ROOT)} "
            f"expected={sha256_hex(expected)} actual={sha256_hex(actual)}"
        )


def _write_without_overwrite(path: Path, payload: bytes, *, replace_existing: bool = False) -> None:
    if path.exists():
        if replace_existing:
            path.write_bytes(payload)
        else:
            _compare(path, payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--replace-provisional",
        action="store_true",
        help="Replace only deterministic T18 outputs created before the T18 checkpoint.",
    )
    args = parser.parse_args()
    if args.check and args.replace_provisional:
        raise ValueError("--check and --replace-provisional are mutually exclusive")
    versioned, raw, summary = build()
    if args.check:
        for path, payload in {**versioned, **raw}.items():
            _compare(path, payload)
        raw_root = ROOT / load_yaml(CONFIG_PATH)["artifacts"]["raw_root"]
        expected = {path.resolve() for path in raw}
        actual = {path.resolve() for path in raw_root.rglob("*") if path.is_file()}
        if actual != expected:
            raise RuntimeError("T18 raw artifact file-set drift")
    else:
        for path, payload in raw.items():
            _write_without_overwrite(path, payload, replace_existing=args.replace_provisional)
        for path, payload in versioned.items():
            _write_without_overwrite(path, payload, replace_existing=args.replace_provisional)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
