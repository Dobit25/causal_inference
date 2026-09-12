"""Reproduce the pinned CausalDS T02 inventory and cohort audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(source_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    expected = manifest["release_inventory"]
    expected_cohorts = manifest["p0_cohorts"]
    expected_graph = expected_cohorts["graph"]
    expected_primary = expected_cohorts["primary_downstream"]
    expected_supplementary = expected_cohorts["supplementary"]
    required_tasks = set(expected_primary["required_task_ids"])

    public_root = source_root / "data" / "benchmark" / "main" / "scenes"
    grading_root = source_root / "data" / "benchmark" / "main" / "scenes_private"
    task_files = sorted(public_root.glob("*/variants/*/tasks.json"))
    ground_truth_files = sorted(grading_root.glob("*/ground_truth.json"))
    schema_files = sorted(public_root.glob("*/variants/*/schema.json"))

    total_tasks = 0
    rung2_tasks = 0
    clean_scenes = 0
    clean_no_latent = 0
    graph_cohort: list[dict[str, Any]] = []
    primary_cohort: list[dict[str, Any]] = []

    for task_path in task_files:
        task_document = load_json(task_path)
        scene_id = str(task_document["scene_id"])
        tasks = task_document["tasks"]
        task_ids = {task["task_id"] for task in tasks}
        ground_truth = load_json(grading_root / scene_id / "ground_truth.json")
        schema = load_json(task_path.with_name("schema.json"))

        variant = task_document["observation_variant"]
        latent_nodes = ground_truth["graph"]["latent_nodes"]
        total_tasks += len(tasks)
        rung2_tasks += sum(task["rung"] == 2 for task in tasks)

        if variant == "clean":
            clean_scenes += 1
            if not latent_nodes:
                clean_no_latent += 1
                graph_cohort.append(
                    {
                        "scene_id": scene_id,
                        "rows": int(schema["n_rows"]),
                        "nodes": len(ground_truth["graph"]["nodes"]),
                    }
                )
                if required_tasks <= task_ids:
                    primary_cohort.append(
                        {
                            "scene_id": scene_id,
                            "rows": int(schema["n_rows"]),
                            "nodes": len(ground_truth["graph"]["nodes"]),
                        }
                    )

    graph_cohort.sort(key=lambda row: row["scene_id"])
    primary_cohort.sort(key=lambda row: row["scene_id"])
    primary_ids = {row["scene_id"] for row in primary_cohort}
    supplementary_cohort = [
        row for row in graph_cohort if row["scene_id"] not in primary_ids
    ]
    audit_files = sorted(task_files + schema_files + ground_truth_files)
    lines = []
    for path in audit_files:
        relative = path.relative_to(source_root).as_posix()
        lines.append(f"{relative}\t{path.stat().st_size}\t{sha256_file(path)}")
    aggregate_hash = hashlib.sha256("\n".join(lines).encode()).hexdigest()

    result = {
        "main_scenes": len(task_files),
        "complete_task_catalogs": len(task_files),
        "ground_truth_files": len(ground_truth_files),
        "complete_catalog_tasks": total_tasks,
        "rung2_tasks": rung2_tasks,
        "clean_scenes": clean_scenes,
        "clean_no_latent_scenes": clean_no_latent,
        "graph_scenes": len(graph_cohort),
        "graph_scene_ids": [row["scene_id"] for row in graph_cohort],
        "primary_downstream_scenes": len(primary_cohort),
        "primary_downstream_scene_ids": [
            row["scene_id"] for row in primary_cohort
        ],
        "supplementary_scenes": len(supplementary_cohort),
        "supplementary_scene_ids": [
            row["scene_id"] for row in supplementary_cohort
        ],
        "graph_row_counts": sorted({row["rows"] for row in graph_cohort}),
        "graph_node_range": [
            min(row["nodes"] for row in graph_cohort),
            max(row["nodes"] for row in graph_cohort),
        ],
        "audit_files": len(audit_files),
        "audit_scope_sha256": aggregate_hash,
    }

    assertions = {
        "main_scenes": expected["main_scenes"],
        "complete_task_catalogs": expected["complete_task_catalogs"],
        "ground_truth_files": expected["ground_truth_files"],
        "complete_catalog_tasks": expected["complete_catalog_tasks"],
        "rung2_tasks": expected["rung2_tasks"],
        "clean_scenes": expected["clean_scenes"],
        "clean_no_latent_scenes": expected["clean_no_latent_scenes"],
        "graph_scenes": expected_graph["scene_count"],
        "graph_scene_ids": expected_graph["scene_ids"],
        "primary_downstream_scenes": expected_primary["scene_count"],
        "primary_downstream_scene_ids": expected_primary["scene_ids"],
        "supplementary_scenes": expected_supplementary["scene_count"],
        "supplementary_scene_ids": expected_supplementary["scene_ids"],
        "audit_files": manifest["audit_scope"]["files"],
        "audit_scope_sha256": manifest["audit_scope"]["aggregate_sha256"],
    }
    mismatches = {
        key: {"expected": value, "actual": result[key]}
        for key, value in assertions.items()
        if result[key] != value
    }
    if mismatches:
        raise RuntimeError(json.dumps({"audit_mismatches": mismatches}, indent=2))

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/manifests/causalds.json"),
    )
    args = parser.parse_args()
    result = audit(args.source_root.resolve(), args.manifest.resolve())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
