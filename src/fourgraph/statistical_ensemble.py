"""Offline contracts for P1-v3 statistical ensemble normalization.

This module deliberately contains no Tetrad/R/API execution.  It provides the
small deterministic operations that must be fixture-tested before live work:
canonical skeleton construction, PAG adjacency extraction, MMPC symmetry
validation, five-way method-level voting, and shared semantic-pair pooling.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
from typing import Any

from fourgraph.partial_graph import Edge, PartialGraph


PRIMARY_METHODS = ("single_boss", "bootstrap_boss", "pc", "mmpc", "fges")
BOOTSTRAP_CANDIDATES = ("C1", "C2", "C3", "C4", "C5", "C6")


def canonical_pair(left: str, right: str) -> Edge:
    left, right = str(left), str(right)
    if left == right:
        raise ValueError("self-loop is forbidden")
    return (left, right) if left < right else (right, left)


def _validate_nodes(nodes: Iterable[str]) -> tuple[str, ...]:
    result = tuple(sorted({str(node) for node in nodes}))
    if not result:
        raise ValueError("node universe must not be empty")
    return result


def canonical_skeleton(
    nodes: Iterable[str], edges: Iterable[Sequence[str]]
) -> frozenset[Edge]:
    """Canonicalize undirected endpoint pairs and reject unknown nodes."""

    universe = set(_validate_nodes(nodes))
    result: set[Edge] = set()
    for edge in edges:
        if len(edge) != 2:
            raise ValueError("skeleton edge must have two endpoints")
        pair = canonical_pair(str(edge[0]), str(edge[1]))
        if set(pair) - universe:
            raise ValueError(f"edge contains unknown node: {pair}")
        if pair in result:
            continue
        result.add(pair)
    return frozenset(result)


def pag_to_skeleton(
    nodes: Iterable[str], edges: Iterable[Mapping[str, Any] | Sequence[Any]]
) -> frozenset[Edge]:
    """Discard PAG endpoint semantics and retain only observed adjacencies.

    Mapping inputs use ``node1``/``node2``; sequence inputs use the first two
    fields. Endpoint marks are intentionally not interpreted.
    """

    universe = set(_validate_nodes(nodes))
    result: set[Edge] = set()
    for edge in edges:
        if isinstance(edge, Mapping):
            try:
                left, right = edge["node1"], edge["node2"]
            except KeyError as exc:
                raise ValueError("PAG edge requires node1 and node2") from exc
        else:
            if len(edge) < 2:
                raise ValueError("PAG edge requires two endpoints")
            left, right = edge[0], edge[1]
        pair = canonical_pair(str(left), str(right))
        if set(pair) - universe:
            raise ValueError(f"PAG edge contains unknown node: {pair}")
        result.add(pair)
    return frozenset(result)


def mmpc_symmetric_skeleton(
    nodes: Iterable[str], adjacency: Mapping[str, Mapping[str, int | bool]]
) -> frozenset[Edge]:
    """Accept only a directly symmetric MMPC adjacency matrix."""

    universe = _validate_nodes(nodes)
    for left in universe:
        if left not in adjacency:
            raise ValueError(f"MMPC matrix missing row {left}")
        for right in universe:
            if right not in adjacency[left]:
                raise ValueError(f"MMPC matrix missing cell {left},{right}")
            if bool(adjacency[left][right]) != bool(adjacency[right][left]):
                raise ValueError(f"MMPC output is asymmetric at {left},{right}")
            if left == right and bool(adjacency[left][right]):
                raise ValueError("MMPC self-loop is forbidden")
    return frozenset(
        canonical_pair(left, right)
        for left, right in combinations(universe, 2)
        if bool(adjacency[left][right])
    )


def primary_majority_skeleton(
    method_skeletons: Mapping[str, Iterable[Sequence[str]]],
    nodes: Iterable[str],
    *,
    minimum_votes: int = 3,
) -> frozenset[Edge]:
    """Build the primary 3/5 method-level skeleton vote."""

    if set(method_skeletons) != set(PRIMARY_METHODS) or len(method_skeletons) != len(PRIMARY_METHODS):
        raise ValueError(
            "primary vote must contain exactly the five method-level votes"
        )
    if minimum_votes != 3:
        raise ValueError("P1-v3 primary ensemble requires a 3/5 vote")
    normalized = {
        method: canonical_skeleton(nodes, method_skeletons[method])
        for method in PRIMARY_METHODS
    }
    universe = _validate_nodes(nodes)
    return frozenset(
        pair
        for pair in combinations(universe, 2)
        if sum(pair in normalized[method] for method in PRIMARY_METHODS)
        >= minimum_votes
    )


def shared_semantic_pair_pool(
    nodes: Iterable[str],
    *,
    single_boss: Iterable[Sequence[str]],
    bootstrap_candidates: Mapping[str, Iterable[Sequence[str]]],
    ensemble: Iterable[Sequence[str]],
) -> frozenset[Edge]:
    """Union eligible undirected edges once, with six candidates retained."""

    if set(bootstrap_candidates) != set(BOOTSTRAP_CANDIDATES) or len(bootstrap_candidates) != len(BOOTSTRAP_CANDIDATES):
        raise ValueError("all six Bootstrap-BOSS candidates are required")
    universe = _validate_nodes(nodes)
    pool = set(canonical_skeleton(universe, single_boss))
    for candidate in BOOTSTRAP_CANDIDATES:
        pool.update(canonical_skeleton(universe, bootstrap_candidates[candidate]))
    pool.update(canonical_skeleton(universe, ensemble))
    maximum = len(universe) * (len(universe) - 1) // 2
    if len(pool) > maximum:
        raise ValueError("semantic pool exceeds complete-graph bound")
    return frozenset(pool)


def graph_for_condition(
    nodes: Iterable[str],
    directed: Iterable[Sequence[str]],
    undirected: Iterable[Sequence[str]],
) -> PartialGraph:
    """Validate a CPDAG-like parent graph without repairing it."""

    graph = PartialGraph.build(nodes, directed, undirected)
    # Validation is deliberately stricter than cycle checking: a failed
    # completed-PDAG check must abort the condition rather than project it.
    from fourgraph.partial_graph import validate_cpdag

    validate_cpdag(graph)
    return graph
