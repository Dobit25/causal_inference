"""Independent topological-order/brute-subset reference for Edge-Selective."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Mapping

from .h2_reference import reference_extensions
from .hybrid_h2 import graph_sha256
from .partial_graph import PartialGraph


@dataclass(frozen=True)
class ReferenceProblem:
    parent: PartialGraph
    rows: tuple[Mapping[str, Any], ...]
    extensions: tuple[PartialGraph, ...]
    scores: tuple[float, ...]
    weights: tuple[float, ...]


def prepare_reference_edge_selective(
    parent: PartialGraph, artifact: Mapping[str, Any]
) -> ReferenceProblem:
    extensions = reference_extensions(parent)
    rows = tuple(sorted(artifact["preferences"], key=lambda row: (row["left"], row["right"])))
    scores = []
    for extension in extensions:
        score = 0.0
        for row in rows:
            left, right = str(row["left"]), str(row["right"])
            probability = float(row["probability_left_causes_right"])
            score += math.log(probability if (left, right) in extension.directed else 1.0 - probability)
        scores.append(score)
    maximum = max(scores)
    values = [math.exp(score - maximum) for score in scores]
    total = math.fsum(values)
    return ReferenceProblem(parent, rows, extensions, tuple(scores), tuple(value / total for value in values))


def _powerset(values: list[dict[str, Any]]):
    for size in range(len(values) + 1):
        yield from combinations(values, size)


def reference_edge_selective(
    parent: PartialGraph,
    artifact: Mapping[str, Any],
    *,
    tau_semantic: float,
    tau_global: float,
) -> dict[str, Any]:
    return solve_prepared_reference(
        prepare_reference_edge_selective(parent, artifact),
        tau_semantic=tau_semantic,
        tau_global=tau_global,
    )


def solve_prepared_reference(
    problem: ReferenceProblem,
    *,
    tau_semantic: float,
    tau_global: float,
) -> dict[str, Any]:
    parent, rows, extensions = problem.parent, problem.rows, problem.extensions
    scores, weights = problem.scores, problem.weights
    candidates: list[dict[str, Any]] = []
    for row in rows:
        left, right = str(row["left"]), str(row["right"])
        probability = float(row["probability_left_causes_right"])
        direction = (left, right) if probability >= 0.5 else (right, left)
        semantic = max(probability, 1.0 - probability)
        support_values = [weights[i] for i, extension in enumerate(extensions) if direction in extension.directed]
        stability = 1.0 if len(support_values) == len(extensions) else math.fsum(support_values)
        if semantic + 1e-15 >= tau_semantic and stability + 1e-15 >= tau_global:
            candidates.append(
                {
                    "left": left,
                    "right": right,
                    "source": direction[0],
                    "target": direction[1],
                    "semantic_confidence": semantic,
                    "global_stability": stability,
                }
            )

    feasible: list[tuple[tuple[Any, ...], tuple[dict[str, Any], ...], list[PartialGraph]]] = []
    for subset in _powerset(candidates):
        directions = {(row["source"], row["target"]) for row in subset}
        compatible = [extension for extension in extensions if directions.issubset(extension.directed)]
        if not compatible:
            continue
        serialized = tuple(sorted(directions))
        key = (
            -math.fsum(float(row["global_stability"]) for row in subset),
            -len(subset),
            -math.fsum(float(row["semantic_confidence"]) for row in subset),
            serialized,
        )
        feasible.append((key, subset, compatible))
    _, selected, compatible = min(feasible, key=lambda item: item[0])
    directed = {
        edge
        for edge in parent.skeleton
        for edge in (edge, (edge[1], edge[0]))
        if all(edge in extension.directed for extension in compatible)
    }
    undirected = parent.skeleton - {tuple(sorted(edge)) for edge in directed}
    output = PartialGraph.build(parent.nodes, directed, undirected)
    selected_pairs = {tuple(sorted((row["source"], row["target"]))) for row in selected}
    provenance = []
    for left, right in sorted(parent.skeleton):
        pair = (left, right)
        if pair not in parent.undirected:
            source, target = ((left, right) if (left, right) in parent.directed else (right, left))
            source_type = "compelled"
        elif pair in output.undirected:
            source = target = None
            source_type = "unresolved"
        elif pair in selected_pairs:
            selected_row = next(row for row in selected if tuple(sorted((row["source"], row["target"]))) == pair)
            source, target = selected_row["source"], selected_row["target"]
            source_type = "semantic_selected"
        else:
            source, target = ((left, right) if (left, right) in output.directed else (right, left))
            source_type = "closure_propagated"
        provenance.append({"left": left, "right": right, "source": source, "target": target, "direction_source": source_type})
    return {
        "parent_graph_sha256": graph_sha256(parent),
        "consistent_extension_count": len(extensions),
        "extension_scores": scores,
        "extension_weights": weights,
        "candidate_directions": candidates,
        "selected_directions": list(selected),
        "compatible_extensions_after_selection": len(compatible),
        "output_graph": output.to_dict(),
        "output_graph_sha256": graph_sha256(output),
        "edge_provenance_core": provenance,
    }
