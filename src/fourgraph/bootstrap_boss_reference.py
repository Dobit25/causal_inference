"""Independently structured reference aggregation for P1-v3 conformance."""

from __future__ import annotations

from collections import Counter
from itertools import combinations

from fourgraph.bootstrap_boss import (
    ADJACENCY_GRID,
    BOOTSTRAP_RUNS,
    DIRECTION_GRID,
    BootstrapBossContractError,
    BootstrapGraphRun,
)
from fourgraph.partial_graph import PartialGraph, consistent_extension


def reference_counts(
    nodes: tuple[str, ...], runs: list[BootstrapGraphRun]
) -> dict[tuple[str, str], dict[str, int]]:
    if len(runs) != BOOTSTRAP_RUNS:
        raise BootstrapBossContractError("reference requires 200 runs")
    if {run.repetition for run in runs} != set(range(BOOTSTRAP_RUNS)):
        raise BootstrapBossContractError("reference run index mismatch")
    output: dict[tuple[str, str], dict[str, int]] = {}
    for left, right in combinations(nodes, 2):
        observed: list[str] = []
        for run in runs:
            if run.graph.nodes != nodes:
                raise BootstrapBossContractError("reference node mismatch")
            directed = set(run.graph.directed)
            undirected = set(run.graph.undirected)
            if (left, right) in directed:
                observed.append("A_to_B")
            elif (right, left) in directed:
                observed.append("B_to_A")
            elif (left, right) in undirected:
                observed.append("undirected")
            else:
                observed.append("absent")
        counts = Counter(observed)
        output[(left, right)] = {
            state: counts.get(state, 0)
            for state in ("absent", "undirected", "A_to_B", "B_to_A")
        }
    return output


def reference_parent_graph(
    nodes: tuple[str, ...],
    counts: dict[tuple[str, str], dict[str, int]],
    *,
    tau_adjacency: float,
    tau_direction: float,
) -> PartialGraph:
    if float(tau_adjacency) not in ADJACENCY_GRID:
        raise BootstrapBossContractError("reference adjacency threshold off grid")
    if float(tau_direction) not in DIRECTION_GRID:
        raise BootstrapBossContractError("reference direction threshold off grid")
    arrows: set[tuple[str, str]] = set()
    lines: set[tuple[str, str]] = set()
    for pair in combinations(nodes, 2):
        values = counts[pair]
        present = BOOTSTRAP_RUNS - values["absent"]
        if present / BOOTSTRAP_RUNS < float(tau_adjacency):
            continue
        left, right = pair
        if values["A_to_B"] / BOOTSTRAP_RUNS >= float(tau_direction):
            arrows.add((left, right))
        elif values["B_to_A"] / BOOTSTRAP_RUNS >= float(tau_direction):
            arrows.add((right, left))
        else:
            lines.add(pair)
    try:
        graph = PartialGraph.build(nodes, arrows, lines)
        consistent_extension(graph)
    except ValueError as exc:
        raise BootstrapBossContractError(
            "reference parent has no consistent extension"
        ) from exc
    return graph
