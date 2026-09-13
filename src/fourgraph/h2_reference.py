"""Independent exhaustive reference implementation for T20 only."""

from __future__ import annotations

import math
from itertools import permutations
from typing import Any, Mapping

from .graph_contract import canonical_json_bytes, sha256_hex
from .partial_graph import PartialGraph, unshielded_colliders, validate_cpdag


def reference_extensions(parent: PartialGraph) -> tuple[PartialGraph, ...]:
    """Enumerate extensions by node orders, independently of production bit search."""
    validate_cpdag(parent)
    colliders = unshielded_colliders(parent)
    found: dict[tuple[tuple[str, str], ...], PartialGraph] = {}
    for order in permutations(parent.nodes):
        position = {node: index for index, node in enumerate(order)}
        directed = {
            (left, right) if position[left] < position[right] else (right, left)
            for left, right in parent.skeleton
        }
        if not parent.directed.issubset(directed):
            continue
        candidate = PartialGraph.build(parent.nodes, directed)
        if unshielded_colliders(candidate) != colliders:
            continue
        key = tuple(sorted(candidate.directed))
        found[key] = candidate
    return tuple(found[key] for key in sorted(found))


def reference_forced(parent: PartialGraph, artifact: Mapping[str, Any]) -> dict[str, Any]:
    rows = sorted(artifact["preferences"], key=lambda row: (row["left"], row["right"]))
    candidates = reference_extensions(parent)

    def score(candidate: PartialGraph) -> float:
        values = []
        for row in rows:
            left, right = row["left"], row["right"]
            p = float(row["probability_left_causes_right"])
            values.append(math.log(p if (left, right) in candidate.directed else 1.0 - p))
        return sum(values)

    scored = [(score(candidate), candidate) for candidate in candidates]
    scored.sort(key=lambda item: (-item[0], tuple(sorted(item[1].directed))))
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else None
    margin: float | str = (
        "infinity" if second is None else (best_score - second) / len(rows)
    )
    conflict_sum = 0.0
    overridden: list[tuple[str, str]] = []
    for row in rows:
        left, right = row["left"], row["right"]
        p = float(row["probability_left_causes_right"])
        local = (left, right) if p >= 0.5 else (right, left)
        selected = (left, right) if (left, right) in best.directed else (right, left)
        if local != selected:
            conflict_sum += abs(p - (1.0 - p))
            overridden.append((left, right))
    conflict = conflict_sum / len(rows) if rows else 0.0
    return {
        "selected_graph": best.to_dict(),
        "selected_graph_sha256": sha256_hex(canonical_json_bytes(best.to_dict())),
        "extension_serializations": [list(map(list, sorted(item.directed))) for item in candidates],
        "consistent_extension_count": len(candidates),
        "best_log_score": best_score,
        "second_best_log_score": second,
        "normalized_margin": margin,
        "normalized_conflict_mass": conflict,
        "overridden_pairs": [list(edge) for edge in sorted(overridden)],
    }


def reference_selective(
    parent: PartialGraph,
    forced: Mapping[str, Any],
    tau_margin: float,
    tau_conflict: float,
) -> tuple[str, dict[str, Any]]:
    margin = forced["normalized_margin"]
    accept = (
        (margin == "infinity" or float(margin) >= float(tau_margin))
        and float(forced["normalized_conflict_mass"]) <= float(tau_conflict)
    )
    return ("accept", forced["selected_graph"]) if accept else ("abstain", parent.to_dict())
