"""Fail-closed successor SCM planning and generation primitives.

The module can generate synthetic conformance blueprints.  Reserved P1-v3
study namespaces are deliberately rejected until a later authorization layer
is versioned and hash-frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from fourgraph.p1_generation import (
    PRIMARY_MOTIFS,
    QUERY_STRATA,
    NOISE_FAMILIES,
    SceneBlueprint,
    _edge_weights,
    _find_query,
    _weakly_connected,
    balanced_assignment,
    graph_motifs,
    seed64,
    task_records_for_query,
)
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact


RESERVED_REAL_NAMESPACES = frozenset({"P1V3D", "P1V3C", "P1V3T"})


class SuccessorGenerationError(ValueError):
    """Raised when a generator/allocator contract is violated."""


@dataclass(frozen=True)
class PlannedScene:
    role: str
    synthetic_id: str
    contract_scene_id: str
    node_count: int
    assigned_primary_motif: str
    noise_family: str
    query_target_stratum: str

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "synthetic_id": self.synthetic_id,
            "contract_scene_id": self.contract_scene_id,
            "node_count": self.node_count,
            "assigned_primary_motif": self.assigned_primary_motif,
            "noise_family": self.noise_family,
            "query_target_stratum": self.query_target_stratum,
        }


def _normalized_counts(
    counts: Mapping[object, object], allowed: Sequence[object], expected_total: int, field: str
) -> dict[object, int]:
    if set(counts) != set(allowed):
        raise SuccessorGenerationError(f"{field} categories do not match contract")
    result: dict[object, int] = {}
    for key in allowed:
        value = counts[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SuccessorGenerationError(f"{field} counts must be non-negative integers")
        result[key] = value
    if sum(result.values()) != expected_total:
        raise SuccessorGenerationError(f"{field} counts do not cover role")
    return result


def allocate_role(
    *,
    role: str,
    namespace: str,
    scene_count: int,
    scene_number_start: int,
    master_seed: int,
    marginals: Mapping[str, Mapping[object, object]],
) -> tuple[PlannedScene, ...]:
    if namespace in RESERVED_REAL_NAMESPACES:
        raise SuccessorGenerationError("reserved real namespace requires later authorization")
    if not role.startswith("SYN") or not namespace.startswith("SYN"):
        raise SuccessorGenerationError("offline allocator accepts synthetic namespaces only")
    if isinstance(scene_count, bool) or not isinstance(scene_count, int) or scene_count <= 0:
        raise SuccessorGenerationError("scene_count must be a positive integer")
    if isinstance(scene_number_start, bool) or not isinstance(scene_number_start, int):
        raise SuccessorGenerationError("scene_number_start must be an integer")
    if isinstance(master_seed, bool) or not isinstance(master_seed, int) or master_seed < 0:
        raise SuccessorGenerationError("master_seed must be a non-negative integer")
    if set(marginals) != {"node_count", "primary_motif", "noise_family", "query_stratum"}:
        raise SuccessorGenerationError("marginal fields do not match contract")

    node_counts = _normalized_counts(marginals["node_count"], (5, 6, 7), scene_count, "node_count")
    motifs = _normalized_counts(
        marginals["primary_motif"], PRIMARY_MOTIFS, scene_count, "primary_motif"
    )
    noises = _normalized_counts(
        marginals["noise_family"], NOISE_FAMILIES, scene_count, "noise_family"
    )
    strata = _normalized_counts(
        marginals["query_stratum"], QUERY_STRATA, scene_count, "query_stratum"
    )
    ids = tuple(f"{namespace}{index:03d}" for index in range(scene_count))
    allocated_nodes = balanced_assignment(ids, node_counts, master_seed, "allocation_node_count")
    allocated_motifs = balanced_assignment(ids, motifs, master_seed, "allocation_primary_motif")
    allocated_noises = balanced_assignment(ids, noises, master_seed, "allocation_noise_family")
    allocated_strata = balanced_assignment(ids, strata, master_seed, "allocation_query_stratum")
    return tuple(
        PlannedScene(
            role=role,
            synthetic_id=synthetic_id,
            contract_scene_id=f"synthetic_scene_{scene_number_start + index:06d}",
            node_count=int(allocated_nodes[synthetic_id]),
            assigned_primary_motif=str(allocated_motifs[synthetic_id]),
            noise_family=str(allocated_noises[synthetic_id]),
            query_target_stratum=str(allocated_strata[synthetic_id]),
        )
        for index, synthetic_id in enumerate(ids)
    )


def generate_blueprint(
    plan: PlannedScene,
    *,
    master_seed: int,
    edge_count_ranges: Mapping[int, Sequence[int]],
    minimum_unresolved_edges: int,
    maximum_attempts: int,
) -> tuple[SceneBlueprint, int]:
    if plan.synthetic_id[:3] != "SYN" or plan.contract_scene_id[:16] != "synthetic_scene_":
        raise SuccessorGenerationError("blueprint generation is restricted to synthetic fixtures")
    if minimum_unresolved_edges < 0 or maximum_attempts <= 0:
        raise SuccessorGenerationError("invalid acceptance limits")
    if set(edge_count_ranges) != {5, 6, 7}:
        raise SuccessorGenerationError("edge-count ranges are incomplete")
    lower, upper = map(int, edge_count_ranges[plan.node_count])
    nodes = tuple(f"X{node:03d}" for node in range(plan.node_count))
    rng = np.random.Generator(
        np.random.PCG64DXSM(seed64(master_seed, plan.synthetic_id, "graph_candidates"))
    )
    accepted: tuple[int, tuple[str, ...], PartialGraph, PartialGraph, tuple[str, ...], str, str] | None = None
    for attempt in range(1, maximum_attempts + 1):
        order = tuple(str(node) for node in rng.permutation(nodes))
        possible = [
            (order[left], order[right])
            for left in range(plan.node_count)
            for right in range(left + 1, plan.node_count)
        ]
        edge_count = int(rng.integers(lower, upper + 1))
        selected = rng.choice(len(possible), size=edge_count, replace=False)
        dag = PartialGraph.build(nodes, directed=[possible[int(position)] for position in selected])
        if not _weakly_connected(dag):
            continue
        motifs = graph_motifs(dag)
        if plan.assigned_primary_motif not in motifs:
            continue
        cpdag = dag_to_cpdag_exact(dag)
        if len(cpdag.undirected) < minimum_unresolved_edges:
            continue
        query = _find_query(
            dag,
            plan.synthetic_id,
            plan.contract_scene_id,
            plan.query_target_stratum,
            seed64(master_seed, plan.synthetic_id, "query_order"),
        )
        if query is None:
            continue
        accepted = (attempt, order, dag, cpdag, motifs, query[0], query[1])
        break
    if accepted is None:
        raise SuccessorGenerationError("synthetic generator exhausted attempts")
    attempt, order, dag, cpdag, motifs, treatment, outcome = accepted
    _, agreements = task_records_for_query(
        dag, plan.synthetic_id, plan.contract_scene_id, treatment, outcome
    )
    components = ("graph_candidates", "edge_weights", "observations", "query_order")
    blueprint = SceneBlueprint(
        study_id=plan.synthetic_id,
        contract_scene_id=plan.contract_scene_id,
        node_count=plan.node_count,
        assigned_primary_motif=plan.assigned_primary_motif,
        noise_family=plan.noise_family,
        query_target_stratum=plan.query_target_stratum,
        generation_attempt=attempt,
        topological_order=order,
        dag=dag,
        oracle_cpdag=cpdag,
        motifs=motifs,
        query_treatment=treatment,
        query_outcome=outcome,
        edge_weights=_edge_weights(dag, master_seed, plan.synthetic_id),
        component_seeds=tuple(
            (component, seed64(master_seed, plan.synthetic_id, component))
            for component in components
        ),
    )
    return blueprint, agreements


def validate_reserved_design_arithmetic(
    roles: Mapping[str, Mapping[str, object]], reserved_namespaces: Sequence[str]
) -> None:
    expected = {"method_development", "semantic_calibration", "threshold_validation"}
    if set(roles) != expected:
        raise SuccessorGenerationError("real role set mismatch")
    namespaces: set[str] = set()
    ranges: list[set[int]] = []
    seeds: set[int] = set()
    for role in sorted(expected):
        row = roles[role]
        namespace = row.get("namespace")
        number_range = row.get("reserved_scene_number_range")
        seed = row.get("master_seed")
        count = row.get("scene_count")
        if namespace not in reserved_namespaces or namespace in namespaces:
            raise SuccessorGenerationError("real namespaces are missing or duplicated")
        if not isinstance(number_range, list) or len(number_range) != 2:
            raise SuccessorGenerationError("reserved range must be [start, stop]")
        start, stop = number_range
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (start, stop, count)):
            raise SuccessorGenerationError("real range/count must be integers")
        if stop - start != count or start >= stop:
            raise SuccessorGenerationError("real range length does not match count")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed in seeds:
            raise SuccessorGenerationError("real master seeds must be distinct integers")
        current = set(range(start, stop))
        if any(current & prior for prior in ranges):
            raise SuccessorGenerationError("real scene ranges overlap")
        namespaces.add(str(namespace))
        seeds.add(seed)
        ranges.append(current)
