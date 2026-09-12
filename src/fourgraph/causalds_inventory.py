"""CausalDS scene inventory and deterministic nested P0 stratification."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median
from typing import Any


PRIMARY_TASK_IDS = (
    "identification__one_valid_adjustment_set",
    "identification__all_minimal_adjustment_sets",
    "identification__minimal_adjustment_set_size",
    "identification__n_valid_adjustment_sets",
    "bias_diagnostic__forbidden_controls_list",
)

NUMERIC_STRATIFICATION_FEATURES = (
    "graph_node_count",
    "graph_edge_density",
    "binary_node_fraction",
    "special_mechanism_node_fraction",
)

CATEGORICAL_STRATIFICATION_FEATURES = (
    "graph_size_band",
    "graph_density_band",
    "data_type_family",
    "structural_label",
)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object."""
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _counter(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def is_dag(nodes: Sequence[str], edges: Sequence[Sequence[str]]) -> bool:
    node_set = set(nodes)
    if len(node_set) != len(nodes):
        return False

    children = {node: [] for node in nodes}
    indegree = {node: 0 for node in nodes}
    seen_edges: set[tuple[str, str]] = set()
    for edge in edges:
        if len(edge) != 2:
            return False
        source, target = edge
        if source not in node_set or target not in node_set or source == target:
            return False
        pair = (source, target)
        if pair in seen_edges:
            return False
        seen_edges.add(pair)
        children[source].append(target)
        indegree[target] += 1

    frontier = sorted(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while frontier:
        node = frontier.pop(0)
        visited += 1
        for child in sorted(children[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                frontier.append(child)
                frontier.sort()
    return visited == len(nodes)


def _graph_size_band(node_count: int) -> str:
    if node_count <= 3:
        return "small_3"
    if node_count <= 5:
        return "medium_4_5"
    return "large_6_plus"


def _density_band(density: float) -> str:
    if density <= 0.5:
        return "sparse_le_0_50"
    if density <= 0.75:
        return "medium_0_50_0_75"
    return "dense_gt_0_75"


def _data_type_family(variable_type_counts: dict[str, int]) -> str:
    present = {name for name, count in variable_type_counts.items() if count}
    if present == {"continuous"}:
        return "continuous_only"
    if present == {"binary"}:
        return "binary_only"
    if present <= {"binary", "continuous"}:
        return "mixed_binary_continuous"
    return "other_mixed"


def build_scene_inventory(
    source_root: Path,
    required_task_ids: Sequence[str] = PRIMARY_TASK_IDS,
) -> list[dict[str, Any]]:
    """Build one metadata-only inventory record for every released scene."""
    source_root = source_root.resolve()
    public_root = source_root / "data" / "benchmark" / "main" / "scenes"
    grading_root = source_root / "data" / "benchmark" / "main" / "scenes_private"
    required_tasks = set(required_task_ids)
    records: list[dict[str, Any]] = []

    for scene_path in sorted(public_root.iterdir()):
        if not scene_path.is_dir():
            continue
        task_paths = sorted((scene_path / "variants").glob("*/tasks.json"))
        if len(task_paths) != 1:
            raise ValueError(
                f"Expected exactly one released variant for {scene_path.name}; "
                f"found {len(task_paths)}"
            )

        task_path = task_paths[0]
        variant_path = task_path.parent
        schema_path = variant_path / "schema.json"
        data_path = variant_path / "data.parquet"
        ground_truth_path = grading_root / scene_path.name / "ground_truth.json"

        task_document = load_json(task_path)
        schema = load_json(schema_path)
        ground_truth = load_json(ground_truth_path)
        if task_document.get("scene_id") != scene_path.name:
            raise ValueError(f"Scene ID mismatch in {task_path}")
        if ground_truth.get("scene_id") != scene_path.name:
            raise ValueError(f"Scene ID mismatch in {ground_truth_path}")

        graph = ground_truth["graph"]
        metadata = ground_truth.get("metadata", {})
        mechanism_metadata = metadata.get("data_mechanisms", {})
        per_node = mechanism_metadata.get("per_node", {})
        mapping = ground_truth.get("mapping", {})
        tasks = task_document.get("tasks", [])
        task_ids = sorted(str(task["task_id"]) for task in tasks)
        task_id_set = set(task_ids)

        nodes = [str(node) for node in graph.get("nodes", [])]
        edges = graph.get("edges", [])
        observed_nodes = [str(node) for node in graph.get("observed_nodes", [])]
        latent_nodes = [str(node) for node in graph.get("latent_nodes", [])]
        node_count = len(nodes)
        edge_count = len(edges)
        max_dag_edges = node_count * (node_count - 1) // 2
        edge_density = edge_count / max_dag_edges if max_dag_edges else 0.0

        variable_type_counts = _counter(
            str(values.get("var_type", "unknown")) for values in per_node.values()
        )
        mechanism_counts = {
            str(key): int(value)
            for key, value in sorted(
                mechanism_metadata.get("mechanism_counts", {}).items()
            )
        }
        noise_counts = {
            str(key): int(value)
            for key, value in sorted(mechanism_metadata.get("noise_counts", {}).items())
        }
        mechanism_family_counts = _counter(
            str(values["mechanism_family"])
            for values in per_node.values()
            if values.get("mechanism_family") is not None
        )
        binary_nodes = variable_type_counts.get("binary", 0)
        special_nodes = len(
            set(mechanism_metadata.get("nn_nodes", []))
            | set(mechanism_metadata.get("heteroscedastic_nodes", []))
            | set(mechanism_metadata.get("discretized_nodes", {}))
        )

        public_columns = schema.get("columns", {})
        public_dtype_counts = _counter(
            str(values.get("dtype", "unknown"))
            for values in public_columns.values()
        )
        public_binary_columns = sum(
            bool(values.get("is_binary")) for values in public_columns.values()
        )
        mapping_complete = set(mapping) == set(nodes)
        mapped_observed_names = {
            mapping[node] for node in observed_nodes if node in mapping
        }
        schema_maps_observed_nodes = mapped_observed_names == set(public_columns)
        dag_valid = is_dag(nodes, edges)

        observation_variant = str(task_document.get("observation_variant"))
        graph_eligible = all(
            (
                observation_variant == "clean",
                not latent_nodes,
                dag_valid,
                mapping_complete,
                schema_maps_observed_nodes,
                data_path.is_file(),
            )
        )
        primary_eligible = graph_eligible and required_tasks <= task_id_set
        supplementary_eligible = graph_eligible and not primary_eligible

        records.append(
            {
                "scene_id": scene_path.name,
                "observation_variant": observation_variant,
                "n_rows": int(schema.get("n_rows", 0)),
                "public_column_count": len(public_columns),
                "public_dtype_counts": public_dtype_counts,
                "public_binary_column_count": public_binary_columns,
                "task_count": len(tasks),
                "task_ids": task_ids,
                "task_type_counts": _counter(
                    str(task.get("task_type", "unknown")) for task in tasks
                ),
                "task_rung_counts": _counter(
                    str(task.get("rung", "unknown")) for task in tasks
                ),
                "symbolic_task_count": sum(
                    bool(task.get("is_symbolic")) for task in tasks
                ),
                "has_primary_task_panel": required_tasks <= task_id_set,
                "graph_node_count": node_count,
                "graph_edge_count": edge_count,
                "graph_edge_density": round(edge_density, 8),
                "graph_size_band": _graph_size_band(node_count),
                "graph_density_band": _density_band(edge_density),
                "observed_node_count": len(observed_nodes),
                "latent_node_count": len(latent_nodes),
                "dag_valid": dag_valid,
                "mapping_complete": mapping_complete,
                "schema_maps_observed_nodes": schema_maps_observed_nodes,
                "structural_label": str(metadata.get("structural_label", "unknown")),
                "motif": str(metadata.get("motif", "unknown")),
                "identifiable": bool(metadata.get("identifiable")),
                "conceptual_variable_type_counts": variable_type_counts,
                "data_type_family": _data_type_family(variable_type_counts),
                "binary_node_fraction": round(
                    binary_nodes / node_count if node_count else 0.0, 8
                ),
                "mechanisms": {
                    "metadata_available": bool(mechanism_metadata),
                    "continuous_scm_profile": mechanism_metadata.get(
                        "continuous_scm_profile"
                    ),
                    "binary_scm_profile": mechanism_metadata.get(
                        "binary_scm_profile"
                    ),
                    "mechanism_counts": mechanism_counts,
                    "mechanism_family_counts": mechanism_family_counts,
                    "noise_counts": noise_counts,
                    "neural_node_count": len(mechanism_metadata.get("nn_nodes", [])),
                    "heteroscedastic_node_count": len(
                        mechanism_metadata.get("heteroscedastic_nodes", [])
                    ),
                    "discretized_node_count": len(
                        mechanism_metadata.get("discretized_nodes", {})
                    ),
                    "complete_for_all_graph_nodes": set(per_node) == set(nodes),
                },
                "special_mechanism_node_fraction": round(
                    special_nodes / node_count if node_count else 0.0, 8
                ),
                "source_files_present": {
                    "tasks_json": task_path.is_file(),
                    "schema_json": schema_path.is_file(),
                    "data_parquet": data_path.is_file(),
                    "ground_truth_json": ground_truth_path.is_file(),
                },
                "cohort_membership": {
                    "graph": graph_eligible,
                    "primary_downstream": primary_eligible,
                    "supplementary": supplementary_eligible,
                },
            }
        )

    if len(records) != 100:
        raise ValueError(f"Expected 100 scenes, found {len(records)}")
    return records


def serialize_inventory(records: Sequence[dict[str, Any]]) -> bytes:
    """Serialize the inventory as canonical JSON Lines."""
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in sorted(records, key=lambda row: row["scene_id"])
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def load_inventory(path: Path) -> list[dict[str, Any]]:
    """Load canonical inventory JSON Lines."""
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at {path}:{line_number}")
            records.append(value)
    return records


def _mean_vector(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    if not vectors:
        raise ValueError("Cannot average an empty collection")
    return tuple(sum(column) / len(vectors) for column in zip(*vectors))


def _feature_vectors(
    graph_records: Sequence[dict[str, Any]],
) -> tuple[dict[str, tuple[float, ...]], dict[str, Any]]:
    numeric_stats: dict[str, dict[str, float]] = {}
    for feature in NUMERIC_STRATIFICATION_FEATURES:
        values = [float(record[feature]) for record in graph_records]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        numeric_stats[feature] = {
            "mean": mean,
            "std": math.sqrt(variance) or 1.0,
        }

    categorical_levels = {
        feature: sorted({str(record[feature]) for record in graph_records})
        for feature in CATEGORICAL_STRATIFICATION_FEATURES
    }
    vectors: dict[str, tuple[float, ...]] = {}
    for record in graph_records:
        vector: list[float] = []
        for feature in NUMERIC_STRATIFICATION_FEATURES:
            stats = numeric_stats[feature]
            vector.append((float(record[feature]) - stats["mean"]) / stats["std"])
        for feature in CATEGORICAL_STRATIFICATION_FEATURES:
            levels = categorical_levels[feature]
            scale = math.sqrt(len(levels))
            value = str(record[feature])
            vector.extend(1.0 / scale if value == level else 0.0 for level in levels)
        vectors[str(record["scene_id"])] = tuple(vector)
    return vectors, {
        "numeric": numeric_stats,
        "categorical_levels": categorical_levels,
    }


def _loss_against_mean(
    selected_ids: Sequence[str],
    target_mean: Sequence[float],
    vectors: dict[str, tuple[float, ...]],
) -> float:
    selected_mean = _mean_vector([vectors[scene_id] for scene_id in selected_ids])
    return sum(
        (selected_value - target_value) ** 2
        for selected_value, target_value in zip(selected_mean, target_mean)
    )


def _required_coverage(
    records: Sequence[dict[str, Any]], minimum_count: int = 3
) -> dict[str, set[str]]:
    required: dict[str, set[str]] = {}
    for feature in CATEGORICAL_STRATIFICATION_FEATURES:
        counts = Counter(str(record[feature]) for record in records)
        required[feature] = {
            level for level, count in counts.items() if count >= minimum_count
        }
    return required


def _coverage_violations(
    selected_records: Sequence[dict[str, Any]],
    required: dict[str, set[str]],
) -> list[str]:
    violations = []
    for feature, levels in required.items():
        selected_levels = {str(record[feature]) for record in selected_records}
        for level in sorted(levels - selected_levels):
            violations.append(f"{feature}:{level}")
    return violations


def _stable_rank(seed: int, restart: int, cohort: str, scene_id: str) -> str:
    payload = f"nested_balance_v1:{seed}:{restart}:{cohort}:{scene_id}"
    return sha256(payload.encode()).hexdigest()


def _round(value: float) -> float:
    return round(value, 8)


def _balance_summary(
    records: Sequence[dict[str, Any]], dev_ids: Sequence[str]
) -> dict[str, Any]:
    dev_set = set(dev_ids)
    dev = [record for record in records if record["scene_id"] in dev_set]
    holdout = [record for record in records if record["scene_id"] not in dev_set]
    numeric: dict[str, Any] = {}
    for feature in NUMERIC_STRATIFICATION_FEATURES:
        all_values = [float(record[feature]) for record in records]
        dev_values = [float(record[feature]) for record in dev]
        holdout_values = [float(record[feature]) for record in holdout]
        all_mean = sum(all_values) / len(all_values)
        variance = sum((value - all_mean) ** 2 for value in all_values) / len(
            all_values
        )
        std = math.sqrt(variance)
        dev_mean = sum(dev_values) / len(dev_values)
        holdout_mean = sum(holdout_values) / len(holdout_values)
        numeric[feature] = {
            "all_mean": _round(all_mean),
            "dev_mean": _round(dev_mean),
            "holdout_mean": _round(holdout_mean),
            "absolute_standardized_mean_difference": _round(
                abs(dev_mean - holdout_mean) / std if std else 0.0
            ),
        }

    categorical: dict[str, Any] = {}
    for feature in CATEGORICAL_STRATIFICATION_FEATURES:
        categorical[feature] = {
            "all": dict(sorted(Counter(str(row[feature]) for row in records).items())),
            "dev": dict(sorted(Counter(str(row[feature]) for row in dev).items())),
            "holdout": dict(
                sorted(Counter(str(row[feature]) for row in holdout).items())
            ),
        }
    return {"numeric": numeric, "categorical": categorical}


def build_provisional_split(
    inventory: Sequence[dict[str, Any]],
    seed: int = 42,
    restarts: int = 64,
) -> dict[str, Any]:
    """Select reproducible nested P0 development/holdout scene IDs."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if restarts < 1:
        raise ValueError("restarts must be positive")

    graph = [row for row in inventory if row["cohort_membership"]["graph"]]
    primary = [
        row for row in inventory if row["cohort_membership"]["primary_downstream"]
    ]
    supplementary = [
        row for row in inventory if row["cohort_membership"]["supplementary"]
    ]
    if (len(graph), len(primary), len(supplementary)) != (33, 27, 6):
        raise ValueError(
            "Expected nested cohort sizes graph=33, primary=27, supplementary=6; "
            f"found {(len(graph), len(primary), len(supplementary))}"
        )

    by_id = {str(row["scene_id"]): row for row in graph}
    graph_ids = sorted(by_id)
    primary_ids = sorted(str(row["scene_id"]) for row in primary)
    supplementary_ids = sorted(str(row["scene_id"]) for row in supplementary)
    vectors, feature_encoding = _feature_vectors(graph)
    graph_required = _required_coverage(graph)
    primary_required = _required_coverage(primary)
    graph_mean = _mean_vector([vectors[scene_id] for scene_id in graph_ids])
    primary_mean = _mean_vector([vectors[scene_id] for scene_id in primary_ids])
    supplementary_mean = _mean_vector(
        [vectors[scene_id] for scene_id in supplementary_ids]
    )

    @lru_cache(maxsize=None)
    def evaluate(
        selected_primary: tuple[str, ...], selected_supplementary: str
    ) -> tuple[int, float, tuple[str, ...]]:
        primary_dev = sorted(selected_primary)
        graph_dev = sorted([*primary_dev, selected_supplementary])
        violations = _coverage_violations(
            [by_id[scene_id] for scene_id in graph_dev], graph_required
        ) + _coverage_violations(
            [by_id[scene_id] for scene_id in primary_dev], primary_required
        )
        loss = (
            _loss_against_mean(graph_dev, graph_mean, vectors)
            + _loss_against_mean(primary_dev, primary_mean, vectors)
            + _loss_against_mean(
                [selected_supplementary], supplementary_mean, vectors
            )
        )
        return len(violations), loss, tuple(graph_dev)

    best: tuple[int, float, tuple[str, ...]] | None = None
    best_primary: list[str] = []
    best_supplementary = ""
    baseline_losses: list[float] = []

    for restart in range(restarts):
        selected_primary = sorted(
            primary_ids,
            key=lambda scene_id: _stable_rank(
                seed, restart, "primary", scene_id
            ),
        )[:7]
        selected_supplementary = min(
            supplementary_ids,
            key=lambda scene_id: _stable_rank(
                seed, restart, "supplementary", scene_id
            ),
        )
        current = evaluate(tuple(selected_primary), selected_supplementary)
        baseline_losses.append(current[1])

        while True:
            candidate_best = current
            candidate_primary = selected_primary
            candidate_supplementary = selected_supplementary
            selected_set = set(selected_primary)
            for outgoing in selected_primary:
                for incoming in primary_ids:
                    if incoming in selected_set:
                        continue
                    proposed = sorted(
                        (selected_set - {outgoing}) | {incoming}
                    )
                    score = evaluate(tuple(proposed), selected_supplementary)
                    if score < candidate_best:
                        candidate_best = score
                        candidate_primary = proposed
                        candidate_supplementary = selected_supplementary
            for proposed_supplementary in supplementary_ids:
                if proposed_supplementary == selected_supplementary:
                    continue
                score = evaluate(tuple(selected_primary), proposed_supplementary)
                if score < candidate_best:
                    candidate_best = score
                    candidate_primary = selected_primary
                    candidate_supplementary = proposed_supplementary
            if candidate_best >= current:
                break
            current = candidate_best
            selected_primary = sorted(candidate_primary)
            selected_supplementary = candidate_supplementary

        if best is None or current < best:
            best = current
            best_primary = sorted(selected_primary)
            best_supplementary = selected_supplementary

    if best is None or best[0] != 0:
        raise RuntimeError("No split satisfying common-stratum coverage was found")

    primary_dev = best_primary
    supplementary_dev = [best_supplementary]
    graph_dev = sorted([*primary_dev, *supplementary_dev])
    primary_holdout = sorted(set(primary_ids) - set(primary_dev))
    supplementary_holdout = sorted(
        set(supplementary_ids) - set(supplementary_dev)
    )
    graph_holdout = sorted(set(graph_ids) - set(graph_dev))
    graph_violations = _coverage_violations(
        [by_id[scene_id] for scene_id in graph_dev], graph_required
    )
    primary_violations = _coverage_violations(
        [by_id[scene_id] for scene_id in primary_dev], primary_required
    )

    return {
        "status": "provisional_until_t04_integrity",
        "algorithm": {
            "name": "deterministic_nested_balance_v1",
            "seed": seed,
            "restarts": restarts,
            "numeric_features": list(NUMERIC_STRATIFICATION_FEATURES),
            "categorical_features": list(CATEGORICAL_STRATIFICATION_FEATURES),
            "objective": (
                "minimize equal-weight graph + primary + supplementary centroid "
                "loss after satisfying common-stratum coverage"
            ),
            "tie_break": "lexicographic scene_id after SHA-256 seeded starts",
            "feature_encoding": feature_encoding,
            "selected_objective_loss": _round(best[1]),
            "baseline_start_median_loss": _round(median(baseline_losses)),
        },
        "cohorts": {
            "graph": {
                "scene_count": 33,
                "dev_ids": graph_dev,
                "holdout_ids": graph_holdout,
            },
            "primary_downstream": {
                "scene_count": 27,
                "tasks_per_scene": 5,
                "required_task_ids": list(PRIMARY_TASK_IDS),
                "dev_ids": primary_dev,
                "holdout_ids": primary_holdout,
            },
            "supplementary": {
                "scene_count": 6,
                "downstream_role": "exploratory_only",
                "pool_with_primary_accuracy": False,
                "dev_ids": supplementary_dev,
                "holdout_ids": supplementary_holdout,
                "available_task_ids_by_scene": {
                    scene_id: by_id[scene_id]["task_ids"]
                    for scene_id in supplementary_ids
                },
            },
        },
        "nesting_checks": {
            "primary_and_supplementary_partition_graph": set(primary_ids)
            | set(supplementary_ids)
            == set(graph_ids)
            and set(primary_ids).isdisjoint(supplementary_ids),
            "dev_partition_matches_graph_dev": set(primary_dev)
            | set(supplementary_dev)
            == set(graph_dev),
            "holdout_partition_matches_graph_holdout": set(primary_holdout)
            | set(supplementary_holdout)
            == set(graph_holdout),
            "one_role_per_scene": set(graph_dev).isdisjoint(graph_holdout),
        },
        "balance_checks": {
            "common_graph_strata_covered": not graph_violations,
            "common_primary_strata_covered": not primary_violations,
            "selected_loss_below_baseline_median": best[1]
            < median(baseline_losses),
            "supplementary_single_dev_limit": (
                "Only one of six supplementary scenes can be development; "
                "full motif coverage is impossible and results remain exploratory."
            ),
        },
        "balance": {
            "graph": _balance_summary(graph, graph_dev),
            "primary_downstream": _balance_summary(primary, primary_dev),
            "supplementary": _balance_summary(
                supplementary, supplementary_dev
            ),
        },
    }


def build_split_manifest(
    inventory: Sequence[dict[str, Any]],
    inventory_bytes: bytes,
    source_manifest: dict[str, Any],
    seed: int = 42,
    restarts: int = 64,
) -> dict[str, Any]:
    """Wrap the deterministic split in provenance and T03 status metadata."""
    split = build_provisional_split(inventory, seed=seed, restarts=restarts)
    return {
        "manifest_version": 1,
        "task": "T03",
        "status": "provisional_until_t04_integrity",
        "not_frozen": True,
        "source": {
            "benchmark": "CausalDS",
            "github_commit": source_manifest["pins"]["github"]["commit"],
            "huggingface_revision": source_manifest["pins"]["huggingface"][
                "revision"
            ],
            "inventory_path": "data/manifests/causalds_scene_inventory.jsonl",
            "inventory_sha256": sha256(inventory_bytes).hexdigest(),
            "inventory_scene_count": len(inventory),
            "metadata_scope": (
                "tasks.json, schema.json, file presence, and grading-only graph/"
                "mechanism metadata; no parquet content inspection"
            ),
        },
        **split,
        "next_gate": (
            "T04 validates parquet/schema/missingness/mappings for all 33 graph "
            "scenes before exact IDs and task manifests become frozen."
        ),
    }


def serialize_manifest(manifest: dict[str, Any]) -> bytes:
    """Serialize a manifest deterministically."""
    return (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
