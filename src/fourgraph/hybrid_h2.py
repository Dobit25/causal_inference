"""Globally constrained H2 orientation and graph-level selective abstention."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping, Sequence

from .graph_contract import (
    STRUCTURE_SCHEMA_VERSION,
    GraphEdge,
    canonical_json_bytes,
    sha256_hex,
)
from .partial_graph import PartialGraph, unshielded_colliders, validate_cpdag


PREFERENCE_SCHEMA = "fourgraph.semantic_preferences.v1"
H2_SCHEMA = "fourgraph.h2_decision.v1"


class H2ContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Preference:
    left: str
    right: str
    probability_left_causes_right: float

    @property
    def pair(self) -> tuple[str, str]:
        return (self.left, self.right)


def graph_sha256(graph: PartialGraph) -> str:
    edges = [GraphEdge.build(left, right, "directed") for left, right in graph.directed]
    edges.extend(GraphEdge.build(left, right, "undirected") for left, right in graph.undirected)
    payload = {
        "schema_version": STRUCTURE_SCHEMA_VERSION,
        "nodes": list(graph.nodes),
        "edges": [edge.to_dict() for edge in sorted(edges)],
    }
    return sha256_hex(canonical_json_bytes(payload))


def _invalid(code: str, message: str) -> H2ContractError:
    return H2ContractError(code, message)


def parse_preferences(
    parent: PartialGraph,
    artifact: Mapping[str, Any],
    *,
    probability_clip: tuple[float, float] = (0.001, 0.999),
) -> tuple[Preference, ...]:
    try:
        validate_cpdag(parent)
    except (TypeError, ValueError) as exc:
        raise _invalid("invalid_cpdag", str(exc)) from exc
    if not isinstance(artifact, Mapping):
        raise _invalid("artifact_type", "Preference artifact must be an object")
    allowed_top = {"schema_version", "parent_graph_sha256", "preferences"}
    if set(artifact) - allowed_top:
        raise _invalid("extra_top_level_field", "Unexpected preference artifact field")
    if artifact.get("schema_version") != PREFERENCE_SCHEMA:
        raise _invalid("schema_version", "Preference schema version mismatch")
    if artifact.get("parent_graph_sha256") != graph_sha256(parent):
        raise _invalid("parent_hash", "Preference parent graph hash mismatch")
    rows = artifact.get("preferences")
    if not isinstance(rows, list):
        raise _invalid("preferences_type", "preferences must be a list")
    parsed: list[Preference] = []
    node_set = set(parent.nodes)
    for row in rows:
        if not isinstance(row, Mapping):
            raise _invalid("preference_row_type", "Preference row must be an object")
        required = {"left", "right", "probability_left_causes_right"}
        if set(row) - required:
            raise _invalid("extra_preference_field", "Unexpected preference row field")
        if set(row) != required:
            raise _invalid("missing_preference_field", "Incomplete preference row")
        left, right = row["left"], row["right"]
        if not isinstance(left, str) or not isinstance(right, str):
            raise _invalid("endpoint_type", "Preference endpoints must be strings")
        if left not in node_set or right not in node_set:
            raise _invalid("unknown_node", "Preference endpoint is outside parent node universe")
        if left >= right:
            raise _invalid("endpoint_order", "Preference endpoints must be lexicographic")
        pair = (left, right)
        if pair not in parent.undirected:
            if pair in parent.skeleton:
                raise _invalid("compelled_edge", "Preference supplied for compelled edge")
            raise _invalid("nonedge", "Preference supplied for nonedge")
        probability = row["probability_left_causes_right"]
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise _invalid("probability_type", "Probability must be a finite number")
        probability = float(probability)
        if not math.isfinite(probability):
            raise _invalid("probability_nonfinite", "Probability must be finite")
        lower, upper = probability_clip
        if probability < lower or probability > upper:
            raise _invalid("probability_range", "Probability is outside frozen clip range")
        parsed.append(Preference(left, right, probability))
    pairs = [item.pair for item in parsed]
    if len(pairs) != len(set(pairs)):
        raise _invalid("duplicate_edge", "Duplicate unresolved-edge preference")
    expected = set(parent.undirected)
    actual = set(pairs)
    if actual != expected:
        raise _invalid("missing_edge", "Every unresolved edge needs exactly one preference")
    return tuple(sorted(parsed, key=lambda item: item.pair))


def enumerate_consistent_extensions(parent: PartialGraph) -> tuple[PartialGraph, ...]:
    """Production enumeration over binary orientations of unresolved edges."""
    try:
        validate_cpdag(parent)
    except (TypeError, ValueError) as exc:
        raise _invalid("invalid_cpdag", str(exc)) from exc
    unresolved = tuple(sorted(parent.undirected))
    target_colliders = unshielded_colliders(parent)
    candidates: list[PartialGraph] = []
    for bits in product((0, 1), repeat=len(unresolved)):
        directed = set(parent.directed)
        for (left, right), bit in zip(unresolved, bits):
            directed.add((left, right) if bit == 0 else (right, left))
        try:
            candidate = PartialGraph.build(parent.nodes, directed)
        except ValueError:
            continue
        if unshielded_colliders(candidate) != target_colliders:
            continue
        candidates.append(candidate)
    if not candidates:
        raise _invalid("no_consistent_extension", "Parent CPDAG has no consistent extension")
    return tuple(sorted(candidates, key=_edge_serialization))


def _edge_serialization(graph: PartialGraph) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(graph.directed))


def _score(graph: PartialGraph, preferences: Sequence[Preference]) -> float:
    total = 0.0
    for preference in preferences:
        probability = (
            preference.probability_left_causes_right
            if preference.pair in graph.directed
            else 1.0 - preference.probability_left_causes_right
        )
        total += math.log(probability)
    return total


def _conflict(graph: PartialGraph, preferences: Sequence[Preference]) -> tuple[float, list[dict[str, Any]]]:
    if not preferences:
        return 0.0, []
    mass = 0.0
    overridden: list[dict[str, Any]] = []
    for preference in preferences:
        local = (
            preference.pair
            if preference.probability_left_causes_right >= 0.5
            else (preference.right, preference.left)
        )
        selected = preference.pair if preference.pair in graph.directed else (preference.right, preference.left)
        if selected != local:
            edge_mass = abs(2.0 * preference.probability_left_causes_right - 1.0)
            mass += edge_mass
            overridden.append(
                {
                    "left": preference.left,
                    "right": preference.right,
                    "probability_left_causes_right": preference.probability_left_causes_right,
                    "locally_preferred": list(local),
                    "globally_selected": list(selected),
                    "preference_margin": edge_mass,
                }
            )
    return mass / len(preferences), overridden


def solve_h2_forced(parent: PartialGraph, artifact: Mapping[str, Any]) -> dict[str, Any]:
    preferences = parse_preferences(parent, artifact)
    extensions = enumerate_consistent_extensions(parent)
    ranked = sorted(
        ((_score(candidate, preferences), candidate) for candidate in extensions),
        key=lambda item: (-item[0], _edge_serialization(item[1])),
    )
    best_score, best = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else None
    unresolved_count = len(preferences)
    normalized_margin: float | str
    if second_score is None:
        normalized_margin = "infinity"
    else:
        normalized_margin = (best_score - second_score) / unresolved_count
    conflict_mass, overridden = _conflict(best, preferences)
    return {
        "schema_version": H2_SCHEMA,
        "method": "H2_FORCED",
        "parent_graph_sha256": graph_sha256(parent),
        "preference_artifact_sha256": sha256_hex(canonical_json_bytes(artifact)),
        "selected_graph": best.to_dict(),
        "selected_graph_sha256": graph_sha256(best),
        "consistent_extension_count": len(extensions),
        "best_log_score": best_score,
        "second_best_log_score": second_score,
        "normalized_margin": normalized_margin,
        "normalized_conflict_mass": conflict_mass,
        "overridden_edges": overridden,
        "tie_breaking": "lexicographic_canonical_edge_serialization",
    }


def solve_h2_selective(
    parent: PartialGraph,
    forced: Mapping[str, Any],
    *,
    tau_margin: float,
    tau_conflict: float,
) -> dict[str, Any]:
    if forced.get("method") != "H2_FORCED" or forced.get("parent_graph_sha256") != graph_sha256(parent):
        raise _invalid("forced_parent", "Selective input is not the corresponding forced result")
    margin = forced["normalized_margin"]
    margin_pass = margin == "infinity" or float(margin) >= float(tau_margin)
    conflict_pass = float(forced["normalized_conflict_mass"]) <= float(tau_conflict)
    accept = margin_pass and conflict_pass
    output_graph = forced["selected_graph"] if accept else parent.to_dict()
    return {
        "schema_version": H2_SCHEMA,
        "method": "H2_SELECTIVE",
        "parent_graph_sha256": graph_sha256(parent),
        "forced_graph_sha256": forced["selected_graph_sha256"],
        "tau_margin": float(tau_margin),
        "tau_conflict": float(tau_conflict),
        "decision": "accept" if accept else "abstain",
        "output_graph": output_graph,
        "output_graph_sha256": sha256_hex(canonical_json_bytes(output_graph)),
        "abstention_semantics": "unchanged_raw_cpdag" if not accept else None,
    }
