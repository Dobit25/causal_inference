"""Offline primary-ensemble amendment contract.

Bootstrap-BOSS contributes one method-level adjacency vote. Direction
stability is deliberately ignored for that vote; C1--C6 remain sensitivity
conditions downstream.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from .statistical_ensemble import canonical_pair, canonical_skeleton, primary_majority_skeleton


METHOD_LEVEL_ADJACENCY_THRESHOLD = 0.80


def bootstrap_method_level_skeleton(
    nodes: Iterable[str], edge_adjacency_stability: Mapping[Sequence[str], float]
) -> frozenset[tuple[str, str]]:
    """Include an adjacency iff its bootstrap stability is at least .80."""

    universe = tuple(sorted({str(node) for node in nodes}))
    if not universe:
        raise ValueError("node universe must not be empty")
    result = set()
    for edge, stability in edge_adjacency_stability.items():
        if len(edge) != 2:
            raise ValueError("edge must have two endpoints")
        pair = canonical_pair(str(edge[0]), str(edge[1]))
        if set(pair) - set(universe):
            raise ValueError("edge contains unknown node")
        if not isinstance(stability, (int, float)) or isinstance(stability, bool) or not 0 <= stability <= 1:
            raise ValueError("stability must be in [0,1]")
        if float(stability) >= METHOD_LEVEL_ADJACENCY_THRESHOLD:
            result.add(pair)
    return frozenset(result)


def primary_ensemble_from_methods(
    nodes: Iterable[str], *, single_boss: Iterable[Sequence[str]], bootstrap_boss: Iterable[Sequence[str]], pc: Iterable[Sequence[str]], mmpc: Iterable[Sequence[str]], fges: Iterable[Sequence[str]]
) -> frozenset[tuple[str, str]]:
    """Apply the frozen outer 3/5 method-level majority."""

    return primary_majority_skeleton({"single_boss": single_boss, "bootstrap_boss": bootstrap_boss, "pc": pc, "mmpc": mmpc, "fges": fges}, nodes)
