from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations
from typing import Iterable


Edge = tuple[str, str]


@dataclass(frozen=True)
class OrientationDecision:
    step: int
    source: str
    target: str
    reason: str = "lexicographic_consistent_extension"
    arbitrary: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "source": self.source,
            "target": self.target,
            "reason": self.reason,
            "arbitrary": self.arbitrary,
        }


def _canonical_pair(a: str, b: str) -> Edge:
    return (a, b) if a < b else (b, a)


@dataclass(frozen=True)
class PartialGraph:
    """A small CPDAG-oriented graph contract with only ``->`` and ``--`` marks."""

    nodes: tuple[str, ...]
    directed: frozenset[Edge]
    undirected: frozenset[Edge]

    @classmethod
    def build(
        cls,
        nodes: Iterable[str],
        directed: Iterable[Edge] = (),
        undirected: Iterable[Edge] = (),
    ) -> "PartialGraph":
        graph = cls(
            tuple(sorted(set(nodes))),
            frozenset((str(a), str(b)) for a, b in directed),
            frozenset(_canonical_pair(str(a), str(b)) for a, b in undirected),
        )
        graph.validate()
        return graph

    def validate(self) -> None:
        node_set = set(self.nodes)
        if len(node_set) != len(self.nodes):
            raise ValueError("Duplicate graph nodes")
        occupied: set[Edge] = set()
        for a, b in self.directed:
            if a == b or a not in node_set or b not in node_set:
                raise ValueError(f"Invalid directed edge: {(a, b)}")
            pair = _canonical_pair(a, b)
            if pair in occupied:
                raise ValueError(f"Duplicate/conflicting adjacency: {pair}")
            occupied.add(pair)
        for a, b in self.undirected:
            if a >= b or a not in node_set or b not in node_set:
                raise ValueError(f"Invalid canonical undirected edge: {(a, b)}")
            if (a, b) in occupied:
                raise ValueError(f"Duplicate/conflicting adjacency: {(a, b)}")
            occupied.add((a, b))
        if not self.is_directed_acyclic():
            raise ValueError("Directed component contains a cycle")

    @property
    def skeleton(self) -> frozenset[Edge]:
        return frozenset(
            {_canonical_pair(a, b) for a, b in self.directed} | set(self.undirected)
        )

    def adjacent(self, a: str, b: str) -> bool:
        return _canonical_pair(a, b) in self.skeleton

    def edge_state(self, a: str, b: str) -> str:
        if _canonical_pair(a, b) in self.undirected:
            return "undirected"
        if (a, b) in self.directed:
            return "forward"
        if (b, a) in self.directed:
            return "reverse"
        return "absent"

    def is_directed_acyclic(self) -> bool:
        indegree = {node: 0 for node in self.nodes}
        children = {node: set() for node in self.nodes}
        for a, b in self.directed:
            children[a].add(b)
            indegree[b] += 1
        ready = sorted(node for node, degree in indegree.items() if degree == 0)
        visited = 0
        while ready:
            node = ready.pop(0)
            visited += 1
            for child in sorted(children[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
                    ready.sort()
        return visited == len(self.nodes)

    def to_dict(self) -> dict[str, object]:
        return {
            "nodes": list(self.nodes),
            "directed": [list(edge) for edge in sorted(self.directed)],
            "undirected": [list(edge) for edge in sorted(self.undirected)],
        }


def unshielded_colliders(graph: PartialGraph) -> frozenset[tuple[str, str, str]]:
    """Return canonical ``(outer_1, middle, outer_2)`` collider triples."""

    parents: dict[str, set[str]] = {node: set() for node in graph.nodes}
    for parent, child in graph.directed:
        parents[child].add(parent)
    colliders: set[tuple[str, str, str]] = set()
    for middle in graph.nodes:
        for left, right in combinations(sorted(parents[middle]), 2):
            if not graph.adjacent(left, right):
                colliders.add((left, middle, right))
    return frozenset(colliders)


def consistent_extension_with_trace(
    cpdag: PartialGraph,
) -> tuple[PartialGraph, tuple[OrientationDecision, ...]]:
    """Return the lexicographically deterministic Dor--Tarsi DAG extension.

    A removable sink has no outgoing arrow, its undirected neighbours form a
    clique, and every such neighbour is adjacent to every directed parent.
    Orienting all of its undirected incident edges into the sink therefore adds
    neither a cycle nor a new unshielded collider.
    """

    remaining = set(cpdag.nodes)
    directed = set(cpdag.directed)
    undirected = set(cpdag.undirected)
    extension = set(cpdag.directed)
    decisions: list[OrientationDecision] = []

    def adjacent_working(a: str, b: str) -> bool:
        pair = _canonical_pair(a, b)
        return pair in undirected or (a, b) in directed or (b, a) in directed

    while remaining:
        chosen: tuple[str, list[str]] | None = None
        for node in sorted(remaining):
            outgoing = {b for a, b in directed if a == node and b in remaining}
            if outgoing:
                continue
            neighbours = sorted(
                other
                for edge in undirected
                if node in edge
                for other in edge
                if other != node and other in remaining
            )
            parents = {
                a for a, b in directed if b == node and a in remaining
            }
            if any(
                not adjacent_working(a, b)
                for a, b in combinations(neighbours, 2)
            ):
                continue
            if any(
                neighbour != parent
                and not adjacent_working(neighbour, parent)
                for neighbour in neighbours
                for parent in parents
            ):
                continue
            chosen = (node, neighbours)
            break

        if chosen is None:
            raise ValueError("PDAG has no consistent DAG extension")

        node, neighbours = chosen
        for neighbour in neighbours:
            extension.add((neighbour, node))
            decisions.append(
                OrientationDecision(
                    step=len(decisions),
                    source=neighbour,
                    target=node,
                )
            )
        directed = {
            (a, b) for a, b in directed if a != node and b != node
        }
        undirected = {
            edge for edge in undirected if node not in edge
        }
        remaining.remove(node)

    dag = PartialGraph.build(cpdag.nodes, extension)
    if dag.skeleton != cpdag.skeleton:
        raise ValueError("Consistent extension changed the skeleton")
    if not cpdag.directed.issubset(dag.directed):
        raise ValueError("Consistent extension reversed a compelled direction")
    if unshielded_colliders(dag) != unshielded_colliders(cpdag):
        raise ValueError("Consistent extension introduced an unshielded collider")
    return dag, tuple(decisions)


def consistent_extension(cpdag: PartialGraph) -> PartialGraph:
    """Return the DAG from :func:`consistent_extension_with_trace`."""

    return consistent_extension_with_trace(cpdag)[0]


def dag_to_cpdag_exact(
    dag: PartialGraph,
    max_edges: int | None = None,
    *,
    max_nodes: int = 8,
) -> PartialGraph:
    """Compute a DAG's CPDAG by exact Markov-equivalence enumeration.

    Every acyclic orientation is induced by at least one topological node order.
    Enumerating orders is bounded by ``n!`` rather than ``2^m`` and is practical
    for the frozen CausalDS graph sizes (3--7 nodes), including dense graphs.
    """

    if dag.undirected:
        raise ValueError("dag_to_cpdag_exact requires a DAG")
    edges = sorted(dag.skeleton)
    if max_edges is not None and len(edges) > max_edges:
        raise ValueError(f"Exact CPDAG conversion limited to {max_edges} edges")
    if len(dag.nodes) > max_nodes:
        raise ValueError(f"Exact CPDAG conversion limited to {max_nodes} nodes")
    target_colliders = unshielded_colliders(dag)
    equivalents: set[frozenset[Edge]] = set()
    for order in permutations(dag.nodes):
        position = {node: index for index, node in enumerate(order)}
        oriented = frozenset(
            (a, b) if position[a] < position[b] else (b, a)
            for a, b in edges
        )
        candidate = PartialGraph.build(dag.nodes, oriented)
        if unshielded_colliders(candidate) == target_colliders:
            equivalents.add(candidate.directed)
    if not equivalents:
        raise ValueError("No Markov-equivalent DAG found")

    directed: set[Edge] = set()
    undirected: set[Edge] = set()
    for a, b in edges:
        if all((a, b) in graph for graph in equivalents):
            directed.add((a, b))
        elif all((b, a) in graph for graph in equivalents):
            directed.add((b, a))
        else:
            undirected.add((a, b))
    return PartialGraph.build(dag.nodes, directed, undirected)


def validate_cpdag(cpdag: PartialGraph, *, max_nodes: int = 8) -> PartialGraph:
    """Validate that a PDAG is the completed PDAG of one DAG extension.

    The returned DAG is the deterministic consistent extension. Comparing the
    exact essential graph of that extension with the input rejects extendable
    but non-completed PDAGs, not just cycles and impossible orientations.
    """

    extension = consistent_extension(cpdag)
    completed = dag_to_cpdag_exact(extension, max_nodes=max_nodes)
    if completed != cpdag:
        raise ValueError("Graph is extendable but is not a completed PDAG")
    return extension


def cpdag_metrics(estimate: PartialGraph, oracle_dag: PartialGraph) -> dict[str, float | int]:
    oracle = dag_to_cpdag_exact(oracle_dag)
    true_skeleton = oracle.skeleton
    estimated_skeleton = estimate.skeleton
    true_positive = len(true_skeleton & estimated_skeleton)
    false_positive = len(estimated_skeleton - true_skeleton)
    false_negative = len(true_skeleton - estimated_skeleton)
    precision = true_positive / len(estimated_skeleton) if estimated_skeleton else 0.0
    recall = true_positive / len(true_skeleton) if true_skeleton else 1.0
    skeleton_f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    correct_compelled = len(estimate.directed & oracle.directed)
    orientation_precision = (
        correct_compelled / len(estimate.directed) if estimate.directed else 1.0
    )
    orientation_recall = (
        correct_compelled / len(oracle.directed) if oracle.directed else 1.0
    )

    cpdag_shd = 0
    for left, right in combinations(oracle.nodes, 2):
        if estimate.edge_state(left, right) != oracle.edge_state(left, right):
            cpdag_shd += 1

    return {
        "skeleton_true_positive": true_positive,
        "skeleton_false_positive": false_positive,
        "skeleton_false_negative": false_negative,
        "skeleton_precision": round(precision, 8),
        "skeleton_recall": round(recall, 8),
        "skeleton_f1": round(skeleton_f1, 8),
        "compelled_orientation_precision": round(orientation_precision, 8),
        "compelled_orientation_recall": round(orientation_recall, 8),
        "unresolved_edge_rate": round(
            len(estimate.undirected) / len(estimated_skeleton)
            if estimated_skeleton
            else 0.0,
            8,
        ),
        "cpdag_shd": cpdag_shd,
    }


def graph_stability(base: PartialGraph, other: PartialGraph) -> dict[str, float]:
    if base.nodes != other.nodes:
        raise ValueError("Cannot compare graphs with different node sets")
    union = base.skeleton | other.skeleton
    intersection = base.skeleton & other.skeleton
    jaccard = len(intersection) / len(union) if union else 1.0
    states = [
        base.edge_state(a, b) == other.edge_state(a, b)
        for a, b in combinations(base.nodes, 2)
    ]
    agreement = sum(states) / len(states) if states else 1.0
    return {
        "skeleton_jaccard": round(jaccard, 8),
        "endpoint_state_agreement": round(agreement, 8),
    }
