"""Deterministic fresh-SCM generation and split utilities for T18."""

from __future__ import annotations

import hashlib
import io
import math
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable, Mapping

import numpy as np

from fourgraph.conformance_audit import independent_target
from fourgraph.graph_contract import canonical_json_bytes, sha256_hex
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact, unshielded_colliders
from fourgraph.reasoner import (
    TASKS,
    TASK_FIELDS,
    ReasonerQuery,
    _valid_adjustment_sets,
    task_semantics,
)


QUERY_STRATA = (
    "valid_empty",
    "one_minimal_nonempty",
    "multiple_minimal",
    "no_valid_adjustment_set",
)
PRIMARY_MOTIFS = ("chain", "fork", "collider", "mediator", "diamond")
NOISE_FAMILIES = ("laplace", "logistic", "student_t_df5")
SPLIT_FEATURES = (
    "node_count",
    "edge_count_band",
    "assigned_primary_motif",
    "oracle_cpdag_unresolved_edge_band",
    "query_target_stratum",
    "exogenous_noise_family",
)


@dataclass(frozen=True)
class SceneBlueprint:
    study_id: str
    contract_scene_id: str
    node_count: int
    assigned_primary_motif: str
    noise_family: str
    query_target_stratum: str
    generation_attempt: int
    topological_order: tuple[str, ...]
    dag: PartialGraph
    oracle_cpdag: PartialGraph
    motifs: tuple[str, ...]
    query_treatment: str
    query_outcome: str
    edge_weights: tuple[tuple[str, str, float], ...]
    component_seeds: tuple[tuple[str, int], ...]


def seed64(master_seed: int, study_id: str, component: str) -> int:
    payload = f"{master_seed}:{study_id}:{component}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def stable_rank(seed: int, *parts: object) -> str:
    payload = ":".join([str(seed), *(str(part) for part in parts)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def npy_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.save(stream, np.asarray(array, dtype="<f8"), allow_pickle=False)
    return stream.getvalue()


def canonical_line(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def graph_motifs(dag: PartialGraph) -> tuple[str, ...]:
    nodes = dag.nodes
    children = {node: set() for node in nodes}
    for parent, child in dag.directed:
        children[parent].add(child)
    motifs: set[str] = set()
    if any(any(children[child] for child in children[node]) for node in nodes):
        motifs.add("chain")
    if any(len(children[node]) >= 2 for node in nodes):
        motifs.add("fork")
    if unshielded_colliders(dag):
        motifs.add("collider")
    if any(len(path) >= 4 for start in nodes for path in _directed_paths(dag, start)):
        motifs.add("mediator")
    for source in nodes:
        for left, right in combinations(sorted(children[source]), 2):
            if children[left] & children[right]:
                motifs.add("diamond")
                break
        if "diamond" in motifs:
            break
    return tuple(sorted(motifs))


def _directed_paths(dag: PartialGraph, start: str) -> tuple[tuple[str, ...], ...]:
    children = {node: set() for node in dag.nodes}
    for parent, child in dag.directed:
        children[parent].add(child)
    paths: list[tuple[str, ...]] = []

    def visit(node: str, path: tuple[str, ...]) -> None:
        for child in sorted(children[node]):
            next_path = path + (child,)
            paths.append(next_path)
            visit(child, next_path)

    visit(start, (start,))
    return tuple(paths)


def _weakly_connected(dag: PartialGraph) -> bool:
    adjacency = {node: set() for node in dag.nodes}
    for left, right in dag.skeleton:
        adjacency[left].add(right)
        adjacency[right].add(left)
    seen = {dag.nodes[0]}
    stack = [dag.nodes[0]]
    while stack:
        node = stack.pop()
        for neighbor in adjacency[node] - seen:
            seen.add(neighbor)
            stack.append(neighbor)
    return len(seen) == len(dag.nodes)


def _graph_view(dag: PartialGraph) -> dict[str, Any]:
    return {
        "schema_version": "fourgraph.reasoner_graph.v1",
        "graph_type": "dag",
        "nodes": list(dag.nodes),
        "edges": [
            {"source": source, "target": target, "mark": "directed"}
            for source, target in sorted(dag.directed)
        ],
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def normalize_target(task_id: str, target: Mapping[str, Any]) -> dict[str, Any]:
    """Canonicalize answer-set ordering without changing answer semantics."""

    accepted = _jsonable(target["accepted"])
    if task_id in {TASKS[0], TASKS[4]}:
        accepted = [sorted(item) if isinstance(item, list) else item for item in accepted]
    elif task_id == TASKS[1]:
        accepted = [
            sorted((sorted(item) for item in answer), key=lambda item: (len(item), item))
            if isinstance(answer, list)
            else answer
            for answer in accepted
        ]
    accepted = sorted(accepted, key=lambda item: json_sort_key(item))
    return {
        "status": str(target["status"]),
        "accepted": accepted,
        "compatible_dag_count": int(target["compatible_dag_count"]),
    }


def json_sort_key(value: Any) -> tuple[int, str]:
    return (len(value) if isinstance(value, list) else -1, canonical_json_bytes(value).decode("utf-8"))


def _query(dag: PartialGraph, scene_id: str, task_id: str, treatment: str, outcome: str) -> ReasonerQuery:
    candidates = tuple(node for node in dag.nodes if node not in {treatment, outcome})
    return ReasonerQuery(
        scene_id=scene_id,
        task_id=task_id,
        treatment=treatment,
        outcome=outcome,
        candidate_variables=candidates,
        response_field=TASK_FIELDS[task_id],
    )


def production_target(dag: PartialGraph, query: ReasonerQuery) -> dict[str, Any]:
    result = task_semantics(dag, query)
    return normalize_target(
        query.task_id,
        {
            "status": "answered",
            "accepted": _jsonable(result.accepted),
            "compatible_dag_count": 1,
        },
    )


def independent_target_for(dag: PartialGraph, query: ReasonerQuery) -> dict[str, Any]:
    row = {
        "task_id": query.task_id,
        "graph": _graph_view(dag),
        "query": {
            "task_id": query.task_id,
            "treatment": query.treatment,
            "outcome": query.outcome,
            "candidate_variables": list(query.candidate_variables),
        },
    }
    return normalize_target(query.task_id, independent_target(row))


def query_stratum(dag: PartialGraph, treatment: str, outcome: str) -> str:
    query = _query(dag, "selection_only", TASKS[0], treatment, outcome)
    valid = _valid_adjustment_sets(dag, query)
    if not valid:
        return "no_valid_adjustment_set"
    if () in valid:
        return "valid_empty"
    minimum = min(map(len, valid))
    minimal = [item for item in valid if len(item) == minimum]
    return "multiple_minimal" if len(minimal) >= 2 else "one_minimal_nonempty"


def task_records_for_query(
    dag: PartialGraph,
    study_id: str,
    contract_scene_id: str,
    treatment: str,
    outcome: str,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    agreements = 0
    for task_id in TASKS:
        query = _query(dag, contract_scene_id, task_id, treatment, outcome)
        production = production_target(dag, query)
        independent = independent_target_for(dag, query)
        if canonical_json_bytes(production) == canonical_json_bytes(independent):
            agreements += 1
        else:
            raise RuntimeError(
                f"Target solvers disagree for {study_id} {task_id}: "
                f"{production!r} != {independent!r}"
            )
        records.append(
            {
                "schema_version": "fourgraph.p1_task_grading.v1",
                "study_id": study_id,
                "scene_id": contract_scene_id,
                "query_id": f"{study_id}:{task_id}",
                "task_id": task_id,
                "query": query.to_dict(),
                "expected": production,
                "solver_agreement": True,
            }
        )
    return records, agreements


def _find_query(
    dag: PartialGraph,
    study_id: str,
    contract_scene_id: str,
    target_stratum: str,
    query_seed: int,
) -> tuple[str, str] | None:
    pairs = [(left, right) for left in dag.nodes for right in dag.nodes if left != right]
    pairs.sort(key=lambda pair: stable_rank(query_seed, study_id, "query_order", *pair))
    for treatment, outcome in pairs:
        if query_stratum(dag, treatment, outcome) != target_stratum:
            continue
        try:
            task_records_for_query(dag, study_id, contract_scene_id, treatment, outcome)
        except RuntimeError:
            continue
        return treatment, outcome
    return None


def balanced_assignment(
    study_ids: Iterable[str], counts: Mapping[Any, int], master_seed: int, component: str
) -> dict[str, Any]:
    ordered_ids = sorted(study_ids, key=lambda scene: stable_rank(master_seed, component, scene))
    slots = [value for value in sorted(counts, key=str) for _ in range(counts[value])]
    if len(ordered_ids) != len(slots):
        raise ValueError(f"Allocation {component} does not cover all scenes")
    return dict(zip(ordered_ids, slots))


def _edge_weights(
    dag: PartialGraph, master_seed: int, study_id: str
) -> tuple[tuple[str, str, float], ...]:
    rng = np.random.Generator(np.random.PCG64DXSM(seed64(master_seed, study_id, "edge_weights")))
    edges = sorted(dag.directed)
    magnitudes = rng.uniform(0.5, 2.0, size=len(edges))
    positive_count = len(edges) // 2 + int(len(edges) % 2 and seed64(master_seed, study_id, "sign_balance") % 2)
    signs = np.array([1.0] * positive_count + [-1.0] * (len(edges) - positive_count))
    rng.shuffle(signs)
    return tuple(
        (source, target, float(magnitude * sign))
        for (source, target), magnitude, sign in zip(edges, magnitudes, signs)
    )


def generate_blueprints(config: Mapping[str, Any]) -> tuple[list[SceneBlueprint], int]:
    master_seed = int(config["randomness"]["master_seed"])
    offset = int(config["identifiers"]["graph_contract_numeric_offset"])
    study_ids = [f"P1S{index:03d}" for index in range(100)]
    node_counts = balanced_assignment(
        study_ids,
        {int(key): int(value) for key, value in config["graph_generation"]["node_count_allocation"].items()},
        master_seed,
        "allocation_node_count",
    )
    motifs = balanced_assignment(
        study_ids,
        {str(key): int(value) for key, value in config["graph_generation"]["primary_motif_allocation"].items()},
        master_seed,
        "allocation_primary_motif",
    )
    noises = balanced_assignment(
        study_ids,
        {str(key): int(value) for key, value in config["scm"]["noise_family_allocation"].items()},
        master_seed,
        "allocation_noise_family",
    )
    strata = balanced_assignment(
        study_ids,
        {str(key): int(value) for key, value in config["tasks"]["query_stratum_allocation"].items()},
        master_seed,
        "allocation_query_stratum",
    )
    max_attempts = int(config["graph_generation"]["maximum_attempts_per_scene"])
    edge_ranges = {
        int(key): tuple(map(int, value))
        for key, value in config["graph_generation"]["edge_count_range_by_nodes"].items()
    }
    blueprints: list[SceneBlueprint] = []
    total_solver_agreements = 0
    for index, study_id in enumerate(study_ids):
        contract_id = f"scene_{offset + index:06d}"
        node_count = int(node_counts[study_id])
        nodes = tuple(f"X{node:03d}" for node in range(node_count))
        rng = np.random.Generator(np.random.PCG64DXSM(seed64(master_seed, study_id, "graph_candidates")))
        accepted: tuple[int, tuple[str, ...], PartialGraph, PartialGraph, tuple[str, ...], str, str] | None = None
        for attempt in range(1, max_attempts + 1):
            order = tuple(str(node) for node in rng.permutation(nodes))
            possible = [(order[i], order[j]) for i in range(node_count) for j in range(i + 1, node_count)]
            lower, upper = edge_ranges[node_count]
            edge_count = int(rng.integers(lower, upper + 1))
            selected = rng.choice(len(possible), size=edge_count, replace=False)
            dag = PartialGraph.build(nodes, directed=[possible[int(position)] for position in selected])
            if not _weakly_connected(dag):
                continue
            present = graph_motifs(dag)
            if motifs[study_id] not in present:
                continue
            cpdag = dag_to_cpdag_exact(dag)
            if len(cpdag.undirected) < int(config["graph_generation"]["acceptance"]["oracle_cpdag_minimum_unresolved_edges"]):
                continue
            query = _find_query(
                dag,
                study_id,
                contract_id,
                strata[study_id],
                seed64(master_seed, study_id, "query_order"),
            )
            if query is None:
                continue
            accepted = (attempt, order, dag, cpdag, present, query[0], query[1])
            break
        if accepted is None:
            raise RuntimeError(f"Generator exhausted {max_attempts} attempts for {study_id}")
        attempt, order, dag, cpdag, present, treatment, outcome = accepted
        _, agreements = task_records_for_query(dag, study_id, contract_id, treatment, outcome)
        total_solver_agreements += agreements
        seeds = tuple(
            (component, seed64(master_seed, study_id, component))
            for component in ("graph_candidates", "edge_weights", "observations", "query_order")
        )
        blueprints.append(
            SceneBlueprint(
                study_id=study_id,
                contract_scene_id=contract_id,
                node_count=node_count,
                assigned_primary_motif=str(motifs[study_id]),
                noise_family=str(noises[study_id]),
                query_target_stratum=str(strata[study_id]),
                generation_attempt=attempt,
                topological_order=order,
                dag=dag,
                oracle_cpdag=cpdag,
                motifs=present,
                query_treatment=treatment,
                query_outcome=outcome,
                edge_weights=_edge_weights(dag, master_seed, study_id),
                component_seeds=seeds,
            )
        )
    return blueprints, total_solver_agreements


def edge_count_band(node_count: int, edge_count: int, ranges: Mapping[int, tuple[int, int]]) -> str:
    lower, upper = ranges[node_count]
    if edge_count == lower:
        return "sparse"
    if edge_count == upper:
        return "dense"
    return "medium"


def unresolved_band(count: int) -> str:
    if count <= 3:
        return "2_3"
    if count <= 5:
        return "4_5"
    return "6_plus"


def split_feature_values(scene: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple((feature, str(scene[feature])) for feature in SPLIT_FEATURES)


def split_objective(
    dev_ids: set[str], metadata: Mapping[str, Mapping[str, Any]], target_fraction: float
) -> float:
    totals: Counter[tuple[str, str]] = Counter()
    dev: Counter[tuple[str, str]] = Counter()
    for scene_id, scene in metadata.items():
        totals.update(split_feature_values(scene))
        if scene_id in dev_ids:
            dev.update(split_feature_values(scene))
    return sum(
        (dev[key] - total * target_fraction) ** 2 / max(total * target_fraction, 1.0)
        for key, total in totals.items()
    )


def deterministic_split(
    metadata: Mapping[str, Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[tuple[str, ...], tuple[str, ...], dict[str, Any]]:
    ids = tuple(sorted(metadata))
    dev_count = int(config["split"]["development_count"])
    seed = int(config["split"]["seed"])
    restarts = int(config["split"]["restarts"])
    fraction = float(config["split"]["target_fraction"])
    rng = np.random.Generator(np.random.PCG64DXSM(seed))
    candidates: list[tuple[float, tuple[str, ...]]] = []
    candidates.append((split_objective(set(ids[:dev_count]), metadata, fraction), ids[:dev_count]))
    for _ in range(restarts):
        chosen = tuple(sorted(str(ids[int(position)]) for position in rng.choice(len(ids), size=dev_count, replace=False)))
        candidates.append((split_objective(set(chosen), metadata, fraction), chosen))
    _, starting = min(candidates, key=lambda item: (item[0], item[1]))
    dev = set(starting)
    current = split_objective(dev, metadata, fraction)
    while True:
        best: tuple[float, tuple[str, ...], str, str] | None = None
        for outgoing in sorted(dev):
            for incoming in sorted(set(ids) - dev):
                candidate_set = (dev - {outgoing}) | {incoming}
                objective = split_objective(candidate_set, metadata, fraction)
                key = (objective, tuple(sorted(candidate_set)), outgoing, incoming)
                if objective < current - 1e-12 and (best is None or key < best):
                    best = key
        if best is None:
            break
        current, _, outgoing, incoming = best
        dev.remove(outgoing)
        dev.add(incoming)
    holdout = set(ids) - dev
    totals: Counter[tuple[str, str]] = Counter()
    dev_counts: Counter[tuple[str, str]] = Counter()
    for scene_id, scene in metadata.items():
        totals.update(split_feature_values(scene))
        if scene_id in dev:
            dev_counts.update(split_feature_values(scene))
    balance = []
    max_deviation = 0
    for key in sorted(totals):
        rounded_target = int(math.floor(totals[key] * fraction + 0.5))
        deviation = abs(dev_counts[key] - rounded_target)
        max_deviation = max(max_deviation, deviation)
        balance.append(
            {
                "feature": key[0],
                "level": key[1],
                "total": totals[key],
                "development": dev_counts[key],
                "holdout": totals[key] - dev_counts[key],
                "rounded_development_target": rounded_target,
                "absolute_deviation": deviation,
            }
        )
    audit = {
        "objective": current,
        "maximum_rounded_marginal_count_deviation": max_deviation,
        "marginal_balance": balance,
    }
    return tuple(sorted(dev)), tuple(sorted(holdout)), audit


def _noise(rng: np.random.Generator, family: str, shape: tuple[int, int]) -> np.ndarray:
    if family == "laplace":
        return rng.laplace(0.0, 1.0 / math.sqrt(2.0), size=shape)
    if family == "logistic":
        return rng.logistic(0.0, math.sqrt(3.0) / math.pi, size=shape)
    if family == "student_t_df5":
        return rng.standard_t(5.0, size=shape) * math.sqrt(3.0 / 5.0)
    raise ValueError(f"Unknown noise family: {family}")


def sample_observations(blueprint: SceneBlueprint, master_seed: int, rows: int) -> np.ndarray:
    nodes = blueprint.dag.nodes
    index = {node: position for position, node in enumerate(nodes)}
    rng = np.random.Generator(np.random.PCG64DXSM(seed64(master_seed, blueprint.study_id, "observations")))
    errors = _noise(rng, blueprint.noise_family, (rows, len(nodes)))
    values = np.zeros_like(errors, dtype=np.float64)
    parent_weights: dict[str, list[tuple[str, float]]] = {node: [] for node in nodes}
    for parent, child, weight in blueprint.edge_weights:
        parent_weights[child].append((parent, weight))
    for node in blueprint.topological_order:
        column = errors[:, index[node]].copy()
        for parent, weight in parent_weights[node]:
            column += weight * values[:, index[parent]]
        values[:, index[node]] = column
    if not np.isfinite(values).all():
        raise RuntimeError(f"Non-finite observations for {blueprint.study_id}")
    return np.asarray(values, dtype="<f8")


def standardize(values: np.ndarray) -> np.ndarray:
    means = values.mean(axis=0)
    scales = values.std(axis=0, ddof=0)
    if np.any(scales == 0) or not np.isfinite(scales).all():
        raise RuntimeError("Cannot standardize constant/non-finite observations")
    return np.asarray((values - means) / scales, dtype="<f8")


def graph_dict(graph: PartialGraph) -> dict[str, Any]:
    return {
        "nodes": list(graph.nodes),
        "directed": [list(edge) for edge in sorted(graph.directed)],
        "undirected": [list(edge) for edge in sorted(graph.undirected)],
    }


def scene_scm_record(blueprint: SceneBlueprint) -> dict[str, Any]:
    return {
        "schema_version": "fourgraph.p1_scm.v1",
        "study_id": blueprint.study_id,
        "scene_id": blueprint.contract_scene_id,
        "variable_mapping": [
            {"column": index, "canonical_id": node, "type": "continuous", "observed": True}
            for index, node in enumerate(blueprint.dag.nodes)
        ],
        "generation_attempt": blueprint.generation_attempt,
        "topological_order": list(blueprint.topological_order),
        "oracle_dag": graph_dict(blueprint.dag),
        "oracle_cpdag": graph_dict(blueprint.oracle_cpdag),
        "edge_weights": [
            {"source": source, "target": target, "weight": weight}
            for source, target, weight in blueprint.edge_weights
        ],
        "intercepts": {node: 0.0 for node in blueprint.dag.nodes},
        "noise_family": blueprint.noise_family,
        "exogenous_variance": 1.0,
        "component_seeds": dict(blueprint.component_seeds),
        "latent_nodes": [],
    }


def task_bundle(blueprint: SceneBlueprint) -> tuple[dict[str, Any], int]:
    tasks, agreements = task_records_for_query(
        blueprint.dag,
        blueprint.study_id,
        blueprint.contract_scene_id,
        blueprint.query_treatment,
        blueprint.query_outcome,
    )
    return {
        "schema_version": "fourgraph.p1_task_bundle.v1",
        "study_id": blueprint.study_id,
        "scene_id": blueprint.contract_scene_id,
        "query_target_stratum": blueprint.query_target_stratum,
        "tasks": tasks,
    }, agreements


def artifact_entry(path: str, payload: bytes) -> dict[str, Any]:
    return {"path": path, "bytes": len(payload), "sha256": sha256_hex(payload)}
