"""Prospective 20-scene validation generator for T21 v3-C.

This module preserves the T18 generator family while using the separately
registered P1V/scene_110xxx namespace and v3-C allocations.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from .p1_generation import (
    SceneBlueprint,
    _edge_weights,
    _find_query,
    _weakly_connected,
    balanced_assignment,
    graph_motifs,
    seed64,
    task_records_for_query,
)
from .partial_graph import PartialGraph, dag_to_cpdag_exact


def generate_validation_blueprints(
    config: Mapping[str, Any],
) -> tuple[list[SceneBlueprint], int]:
    identifiers = config["identifiers"]
    start, end = map(int, identifiers["study_index_range"])
    count = int(identifiers["count"])
    if end - start + 1 != count:
        raise ValueError("Validation ID range does not match count")
    prefix = str(identifiers["study_id_prefix"])
    study_ids = [f"{prefix}{index:03d}" for index in range(start, end + 1)]
    master_seed = int(config["randomness"]["master_seed"])
    offset = int(identifiers["graph_contract_numeric_offset"])
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
    edge_ranges = {
        int(key): tuple(map(int, value))
        for key, value in config["graph_generation"]["edge_count_range_by_nodes"].items()
    }
    max_attempts = int(config["graph_generation"]["maximum_attempts_per_scene"])
    minimum_unresolved = int(config["graph_generation"]["acceptance"]["oracle_cpdag_minimum_unresolved_edges"])
    blueprints: list[SceneBlueprint] = []
    total_agreements = 0
    for ordinal, study_id in enumerate(study_ids):
        scene_id = f"scene_{offset + ordinal:06d}"
        node_count = int(node_counts[study_id])
        nodes = tuple(f"X{index:03d}" for index in range(node_count))
        rng = np.random.Generator(np.random.PCG64DXSM(seed64(master_seed, study_id, "graph_candidates")))
        accepted = None
        for attempt in range(1, max_attempts + 1):
            order = tuple(str(node) for node in rng.permutation(nodes))
            possible = [(order[i], order[j]) for i in range(node_count) for j in range(i + 1, node_count)]
            lower, upper = edge_ranges[node_count]
            edge_count = int(rng.integers(lower, upper + 1))
            chosen = rng.choice(len(possible), size=edge_count, replace=False)
            dag = PartialGraph.build(nodes, directed=[possible[int(position)] for position in chosen])
            if not _weakly_connected(dag):
                continue
            present = graph_motifs(dag)
            if motifs[study_id] not in present:
                continue
            cpdag = dag_to_cpdag_exact(dag)
            if len(cpdag.undirected) < minimum_unresolved:
                continue
            query = _find_query(
                dag,
                study_id,
                scene_id,
                str(strata[study_id]),
                seed64(master_seed, study_id, "query_order"),
            )
            if query is None:
                continue
            accepted = (attempt, order, dag, cpdag, present, query)
            break
        if accepted is None:
            raise RuntimeError(f"Validation generator exhausted for {study_id}")
        attempt, order, dag, cpdag, present, query = accepted
        _, agreements = task_records_for_query(dag, study_id, scene_id, query[0], query[1])
        total_agreements += agreements
        seeds = tuple(
            (component, seed64(master_seed, study_id, component))
            for component in ("graph_candidates", "edge_weights", "observations", "query_order")
        )
        blueprints.append(
            SceneBlueprint(
                study_id=study_id,
                contract_scene_id=scene_id,
                node_count=node_count,
                assigned_primary_motif=str(motifs[study_id]),
                noise_family=str(noises[study_id]),
                query_target_stratum=str(strata[study_id]),
                generation_attempt=attempt,
                topological_order=order,
                dag=dag,
                oracle_cpdag=cpdag,
                motifs=present,
                query_treatment=query[0],
                query_outcome=query[1],
                edge_weights=_edge_weights(dag, master_seed, study_id),
                component_seeds=seeds,
            )
        )
    return blueprints, total_agreements
