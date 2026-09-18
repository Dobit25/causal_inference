"""Exact credible-extension Edge-Selective orientation for small CPDAGs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from typing import Any, Iterable, Mapping, Sequence

from .graph_contract import canonical_json_bytes, sha256_hex
from .hybrid_h2 import (
    H2ContractError,
    Preference,
    enumerate_consistent_extensions,
    graph_sha256,
    parse_preferences,
)
from .partial_graph import PartialGraph, validate_cpdag


EDGE_SELECTIVE_SCHEMA = "fourgraph.edge_selective_decision.v1"
PARTIAL_GRAPH_SCHEMA = "fourgraph.edge_selective_partial_graph.v1"


@dataclass(frozen=True)
class CandidateDirection:
    left: str
    right: str
    source: str
    target: str
    semantic_confidence: float
    global_stability: float

    @property
    def pair(self) -> tuple[str, str]:
        return (self.left, self.right)

    @property
    def direction(self) -> tuple[str, str]:
        return (self.source, self.target)

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "source": self.source,
            "target": self.target,
            "semantic_confidence": self.semantic_confidence,
            "global_stability": self.global_stability,
        }


@dataclass(frozen=True)
class EdgeSelectiveProblem:
    parent: PartialGraph
    preference_artifact_sha256: str
    preferences: tuple[Preference, ...]
    extensions: tuple[PartialGraph, ...]
    extension_scores: tuple[float, ...]
    extension_weights: tuple[float, ...]


def _invalid(code: str, message: str) -> H2ContractError:
    return H2ContractError(code, message)


def _validate_threshold(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid("threshold_type", f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.5 <= number <= 1.0:
        raise _invalid("threshold_range", f"{name} must be in [0.5, 1.0]")
    return number


def _score(extension: PartialGraph, preferences: Sequence[Preference]) -> float:
    return sum(
        math.log(
            item.probability_left_causes_right
            if item.pair in extension.directed
            else 1.0 - item.probability_left_causes_right
        )
        for item in preferences
    )


def _normalized_extension_weights(
    extensions: Sequence[PartialGraph], preferences: Sequence[Preference]
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    scores = tuple(_score(extension, preferences) for extension in extensions)
    maximum = max(scores)
    unnormalized = tuple(math.exp(score - maximum) for score in scores)
    denominator = math.fsum(unnormalized)
    weights = tuple(value / denominator for value in unnormalized)
    return scores, weights


@lru_cache(maxsize=512)
def _parent_extensions(parent: PartialGraph) -> tuple[PartialGraph, ...]:
    """Cache exact extensions for repeated frozen-threshold evaluation of one parent."""
    return enumerate_consistent_extensions(parent)


def _stability(
    direction: tuple[str, str],
    extensions: Sequence[PartialGraph],
    weights: Sequence[float],
) -> float:
    supported = [weights[index] for index, extension in enumerate(extensions) if direction in extension.directed]
    if len(supported) == len(extensions):
        return 1.0
    return math.fsum(supported)


def _candidate_directions(
    preferences: Sequence[Preference],
    extensions: Sequence[PartialGraph],
    weights: Sequence[float],
    tau_semantic: float,
    tau_global: float,
) -> tuple[CandidateDirection, ...]:
    rows: list[CandidateDirection] = []
    for item in preferences:
        probability = item.probability_left_causes_right
        direction = item.pair if probability >= 0.5 else (item.right, item.left)
        semantic_confidence = max(probability, 1.0 - probability)
        global_stability = _stability(direction, extensions, weights)
        if semantic_confidence + 1e-15 < tau_semantic or global_stability + 1e-15 < tau_global:
            continue
        rows.append(
            CandidateDirection(
                item.left,
                item.right,
                direction[0],
                direction[1],
                semantic_confidence,
                global_stability,
            )
        )
    return tuple(sorted(rows, key=lambda row: row.pair))


def _selection_key(rows: Sequence[CandidateDirection]) -> tuple[Any, ...]:
    directions = tuple(sorted(row.direction for row in rows))
    return (
        -math.fsum(row.global_stability for row in rows),
        -len(rows),
        -math.fsum(row.semantic_confidence for row in rows),
        directions,
    )


def _select_compatible_candidates(
    candidates: Sequence[CandidateDirection], extensions: Sequence[PartialGraph]
) -> tuple[tuple[CandidateDirection, ...], tuple[PartialGraph, ...]]:
    alternatives: dict[tuple[tuple[str, str], ...], tuple[tuple[CandidateDirection, ...], list[PartialGraph]]] = {}
    for extension in extensions:
        selected = tuple(row for row in candidates if row.direction in extension.directed)
        key = tuple(row.direction for row in selected)
        if key not in alternatives:
            alternatives[key] = (selected, [])
        alternatives[key][1].append(extension)
    chosen_rows, _ = min(alternatives.values(), key=lambda item: _selection_key(item[0]))
    chosen_directions = {row.direction for row in chosen_rows}
    compatible = tuple(
        extension
        for extension in extensions
        if chosen_directions.issubset(extension.directed)
    )
    return tuple(chosen_rows), compatible


def _orient(graph: PartialGraph, source: str, target: str) -> PartialGraph:
    pair = tuple(sorted((source, target)))
    if pair not in graph.undirected:
        raise ValueError("Meek rule attempted to orient a non-undirected edge")
    return PartialGraph.build(
        graph.nodes,
        set(graph.directed) | {(source, target)},
        set(graph.undirected) - {pair},
    )


def _r1(graph: PartialGraph, left: str, right: str) -> tuple[str, str] | None:
    for source, middle in sorted(graph.directed):
        if middle == left and not graph.adjacent(source, right):
            return (left, right)
        if middle == right and not graph.adjacent(source, left):
            return (right, left)
    return None


def _r2(graph: PartialGraph, left: str, right: str) -> tuple[str, str] | None:
    for source, target in ((left, right), (right, left)):
        if any((source, middle) in graph.directed and (middle, target) in graph.directed for middle in graph.nodes):
            return (source, target)
    return None


def _r3(graph: PartialGraph, left: str, right: str) -> tuple[str, str] | None:
    for source, target in ((left, right), (right, left)):
        witnesses = sorted(
            node
            for node in graph.nodes
            if tuple(sorted((source, node))) in graph.undirected and (node, target) in graph.directed
        )
        if any(not graph.adjacent(first, second) for first, second in combinations(witnesses, 2)):
            return (source, target)
    return None


def _r4(graph: PartialGraph, left: str, right: str) -> tuple[str, str] | None:
    for source, target in ((left, right), (right, left)):
        for first in sorted(graph.nodes):
            if tuple(sorted((source, first))) not in graph.undirected or graph.adjacent(first, target):
                continue
            if any((first, middle) in graph.directed and (middle, target) in graph.directed for middle in graph.nodes):
                return (source, target)
    return None


def meek_closure(
    parent: PartialGraph,
    selected_directions: Iterable[tuple[str, str]],
) -> tuple[PartialGraph, tuple[dict[str, Any], ...]]:
    """Orient selected background knowledge and apply deterministic Meek R1--R4."""
    validate_cpdag(parent)
    graph = parent
    trace: list[dict[str, Any]] = []
    for source, target in sorted(set(selected_directions)):
        graph = _orient(graph, source, target)
        trace.append({"step": len(trace), "source": source, "target": target, "rule": "semantic_selected"})
    rules = (("R1", _r1), ("R2", _r2), ("R3", _r3), ("R4", _r4))
    while True:
        changed = False
        for rule_name, rule in rules:
            for left, right in sorted(graph.undirected):
                direction = rule(graph, left, right)
                if direction is None:
                    continue
                graph = _orient(graph, *direction)
                trace.append({"step": len(trace), "source": direction[0], "target": direction[1], "rule": rule_name})
                changed = True
                break
            if changed:
                break
        if not changed:
            break
    return graph, tuple(trace)


def _edge_provenance(
    parent: PartialGraph,
    output: PartialGraph,
    selected: Sequence[CandidateDirection],
    trace: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    selected_by_pair = {row.pair: row for row in selected}
    closure_by_pair = {
        tuple(sorted((str(row["source"]), str(row["target"])))): row
        for row in trace
        if row["rule"] != "semantic_selected"
    }
    rows: list[dict[str, Any]] = []
    for left, right in sorted(parent.skeleton):
        pair = (left, right)
        if pair in parent.undirected:
            if pair in output.undirected:
                source = target = None
                direction_source = "unresolved"
                confidence = stability = rule = None
            elif pair in selected_by_pair:
                item = selected_by_pair[pair]
                source, target = item.direction
                direction_source = "semantic_selected"
                confidence, stability, rule = item.semantic_confidence, item.global_stability, None
            else:
                item = closure_by_pair[pair]
                source, target = str(item["source"]), str(item["target"])
                direction_source = "closure_propagated"
                confidence = stability = None
                rule = str(item["rule"])
        else:
            source, target = ((left, right) if (left, right) in parent.directed else (right, left))
            direction_source = "compelled"
            confidence = stability = rule = None
        rows.append(
            {
                "left": left,
                "right": right,
                "mark": "undirected" if direction_source == "unresolved" else "directed",
                "source": source,
                "target": target,
                "direction_source": direction_source,
                "semantic_confidence": confidence,
                "global_stability": stability,
                "closure_rule": rule,
            }
        )
    return tuple(rows)


def validate_edge_selective_output(parent: PartialGraph, result: Mapping[str, Any]) -> PartialGraph:
    if result.get("schema_version") != EDGE_SELECTIVE_SCHEMA or result.get("method") != "H2_EDGE_SELECTIVE":
        raise _invalid("output_schema", "Edge-Selective decision schema mismatch")
    if result.get("parent_graph_sha256") != graph_sha256(parent):
        raise _invalid("output_parent", "Output parent graph hash mismatch")
    record = result.get("output_graph")
    if not isinstance(record, Mapping):
        raise _invalid("output_graph", "Output graph must be an object")
    try:
        graph = PartialGraph.build(record["nodes"], record.get("directed", ()), record.get("undirected", ()))
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid("output_graph", str(exc)) from exc
    if graph.nodes != parent.nodes or graph.skeleton != parent.skeleton:
        raise _invalid("output_structure", "Output changed parent nodes or skeleton")
    if not parent.directed.issubset(graph.directed):
        raise _invalid("output_compelled", "Output reversed a parent compelled direction")
    extensions = _parent_extensions(parent)
    compatible = [extension for extension in extensions if graph.directed.issubset(extension.directed)]
    if not compatible:
        raise _invalid("output_extension", "Output has no parent-consistent DAG extension")
    provenance = result.get("edge_provenance")
    if not isinstance(provenance, list) or len(provenance) != len(parent.skeleton):
        raise _invalid("output_provenance", "Output needs one provenance row per parent adjacency")
    if {tuple((row.get("left"), row.get("right"))) for row in provenance} != set(parent.skeleton):
        raise _invalid("output_provenance", "Output provenance does not cover exact parent skeleton")
    allowed = {"compelled", "semantic_selected", "closure_propagated", "unresolved"}
    if any(row.get("direction_source") not in allowed for row in provenance):
        raise _invalid("output_provenance", "Unknown direction provenance source")
    if result.get("output_graph_sha256") != graph_sha256(graph):
        raise _invalid("output_hash", "Output graph hash mismatch")
    return graph


def prepare_edge_selective(parent: PartialGraph, artifact: Mapping[str, Any]) -> EdgeSelectiveProblem:
    """Validate immutable inputs and precompute the exact credible extension distribution."""
    preferences = parse_preferences(parent, artifact)
    extensions = _parent_extensions(parent)
    scores, weights = _normalized_extension_weights(extensions, preferences)
    return EdgeSelectiveProblem(
        parent=parent,
        preference_artifact_sha256=sha256_hex(canonical_json_bytes(artifact)),
        preferences=preferences,
        extensions=extensions,
        extension_scores=scores,
        extension_weights=weights,
    )


def solve_prepared_edge_selective(
    problem: EdgeSelectiveProblem,
    *,
    tau_semantic: float,
    tau_global: float,
) -> dict[str, Any]:
    """Solve one frozen threshold candidate without recomputing the extension universe."""
    parent = problem.parent
    tau_semantic = _validate_threshold(tau_semantic, "tau_semantic")
    tau_global = _validate_threshold(tau_global, "tau_global")
    extensions = problem.extensions
    scores, weights = problem.extension_scores, problem.extension_weights
    candidates = _candidate_directions(
        problem.preferences, extensions, weights, tau_semantic, tau_global
    )
    selected, supporting_extensions = _select_compatible_candidates(candidates, extensions)
    output, trace = meek_closure(parent, (row.direction for row in selected))
    if not any(output.directed.issubset(extension.directed) for extension in supporting_extensions):
        raise RuntimeError("Meek closure escaped the selected compatible extension set")
    provenance = _edge_provenance(parent, output, selected, trace)
    counts = {
        source: sum(row["direction_source"] == source for row in provenance)
        for source in ("compelled", "semantic_selected", "closure_propagated", "unresolved")
    }
    result = {
        "schema_version": EDGE_SELECTIVE_SCHEMA,
        "method": "H2_EDGE_SELECTIVE",
        "parent_graph_sha256": graph_sha256(parent),
        "preference_artifact_sha256": problem.preference_artifact_sha256,
        "tau_semantic": tau_semantic,
        "tau_global": tau_global,
        "consistent_extension_count": len(extensions),
        "extension_scores": list(scores),
        "extension_weights": list(weights),
        "candidate_directions": [row.to_dict() for row in candidates],
        "selected_directions": [row.to_dict() for row in selected],
        "compatible_extensions_after_selection": len(supporting_extensions),
        "closure_trace": list(trace),
        "output_graph_schema_version": PARTIAL_GRAPH_SCHEMA,
        "output_graph": output.to_dict(),
        "output_graph_sha256": graph_sha256(output),
        "edge_provenance": list(provenance),
        "direction_counts": counts,
        "tie_breaking": "sum_stability_then_count_then_sum_semantic_then_lexicographic",
    }
    validate_edge_selective_output(parent, result)
    return result


def solve_edge_selective(
    parent: PartialGraph,
    artifact: Mapping[str, Any],
    *,
    tau_semantic: float,
    tau_global: float,
) -> dict[str, Any]:
    return solve_prepared_edge_selective(
        prepare_edge_selective(parent, artifact),
        tau_semantic=tau_semantic,
        tau_global=tau_global,
    )


def score_edge_selective(
    parent: PartialGraph, result: Mapping[str, Any], oracle_dag: PartialGraph
) -> dict[str, Any]:
    output = validate_edge_selective_output(parent, result)
    if oracle_dag.undirected or oracle_dag.nodes != parent.nodes:
        raise ValueError("Oracle must be a DAG on the parent node universe")
    answered = [
        row
        for row in result["edge_provenance"]
        if row["direction_source"] in {"semantic_selected", "closure_propagated"}
    ]
    direct = [row for row in answered if row["direction_source"] == "semantic_selected"]
    closure = [row for row in answered if row["direction_source"] == "closure_propagated"]

    def correct(rows: Sequence[Mapping[str, Any]]) -> int:
        return sum((str(row["source"]), str(row["target"])) in oracle_dag.directed for row in rows)

    def precision(rows: Sequence[Mapping[str, Any]]) -> float | None:
        return correct(rows) / len(rows) if rows else None

    return {
        "answered_edges": len(answered),
        "correct_answered_edges": correct(answered),
        "selective_orientation_precision": precision(answered),
        "orientation_coverage": len(answered) / len(parent.undirected) if parent.undirected else 0.0,
        "direct_semantic_answered": len(direct),
        "direct_semantic_correct": correct(direct),
        "direct_semantic_precision": precision(direct),
        "closure_answered": len(closure),
        "closure_correct": correct(closure),
        "closure_precision": precision(closure),
        "unresolved_edges": len(output.undirected),
        "graph_valid": True,
    }
