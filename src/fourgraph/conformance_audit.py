"""Independent reference checks for the T12 synthetic conformance suite."""

from __future__ import annotations

from itertools import combinations, product
from typing import Any, Iterable

from fourgraph.reasoner import TASKS


Edge = tuple[str, str]


def _children(nodes: Iterable[str], edges: set[Edge]) -> dict[str, set[str]]:
    result = {node: set() for node in nodes}
    for parent, child in edges:
        result[parent].add(child)
    return result


def _parents(nodes: Iterable[str], edges: set[Edge]) -> dict[str, set[str]]:
    result = {node: set() for node in nodes}
    for parent, child in edges:
        result[child].add(parent)
    return result


def _reachable(start: str, adjacency: dict[str, set[str]]) -> set[str]:
    result: set[str] = set()
    stack = list(adjacency[start])
    while stack:
        node = stack.pop()
        if node not in result:
            result.add(node)
            stack.extend(adjacency[node])
    return result


def _acyclic(nodes: tuple[str, ...], edges: set[Edge]) -> bool:
    children = _children(nodes, edges)
    state = {node: 0 for node in nodes}

    def visit(node: str) -> bool:
        state[node] = 1
        for child in children[node]:
            if state[child] == 1 or (state[child] == 0 and not visit(child)):
                return False
        state[node] = 2
        return True

    return all(state[node] != 0 or visit(node) for node in nodes)


def _skeleton(edges: set[Edge]) -> set[frozenset[str]]:
    return {frozenset(edge) for edge in edges}


def _colliders(
    nodes: tuple[str, ...],
    edges: set[Edge],
    *,
    adjacency_skeleton: set[frozenset[str]] | None = None,
) -> set[tuple[str, str, str]]:
    parents = _parents(nodes, edges)
    skeleton = adjacency_skeleton if adjacency_skeleton is not None else _skeleton(edges)
    result: set[tuple[str, str, str]] = set()
    for middle in nodes:
        for left, right in combinations(sorted(parents[middle]), 2):
            if frozenset((left, right)) not in skeleton:
                result.add((left, middle, right))
    return result


def _compatible_dags(graph: dict[str, Any]) -> list[set[Edge]]:
    nodes = tuple(graph["nodes"])
    fixed = {
        (edge["source"], edge["target"])
        for edge in graph["edges"]
        if edge["mark"] == "directed"
    }
    undirected = [
        (edge["source"], edge["target"])
        for edge in graph["edges"]
        if edge["mark"] == "undirected"
    ]
    full_skeleton = _skeleton(fixed | set(undirected))
    target_colliders = _colliders(
        nodes, fixed, adjacency_skeleton=full_skeleton
    )
    found: dict[tuple[Edge, ...], set[Edge]] = {}
    for choices in product((0, 1), repeat=len(undirected)):
        edges = set(fixed)
        for (left, right), choice in zip(undirected, choices):
            edges.add((left, right) if choice == 0 else (right, left))
        if _acyclic(nodes, edges) and _colliders(nodes, edges) == target_colliders:
            found[tuple(sorted(edges))] = edges
    if not found:
        raise ValueError("Independent audit found no compatible DAG")
    return [found[key] for key in sorted(found)]


def _directed_paths(
    nodes: tuple[str, ...], edges: set[Edge], start: str, end: str
) -> list[list[str]]:
    children = _children(nodes, edges)
    result: list[list[str]] = []

    def visit(node: str, path: list[str]) -> None:
        if node == end:
            result.append(path)
            return
        for child in sorted(children[node]):
            if child not in path:
                visit(child, path + [child])

    visit(start, [start])
    return result


def _simple_paths(
    nodes: tuple[str, ...], edges: set[Edge], start: str, end: str
) -> list[list[str]]:
    adjacency = {node: set() for node in nodes}
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    result: list[list[str]] = []

    def visit(node: str, path: list[str]) -> None:
        if node == end:
            result.append(path)
            return
        for neighbor in sorted(adjacency[node]):
            if neighbor not in path:
                visit(neighbor, path + [neighbor])

    visit(start, [start])
    return result


def _d_separated_by_active_paths(
    nodes: tuple[str, ...],
    edges: set[Edge],
    left: str,
    right: str,
    conditioned: set[str],
) -> bool:
    children = _children(nodes, edges)
    conditioned_or_ancestors = set(conditioned)
    for node in conditioned:
        parents = _parents(nodes, edges)
        reverse = {name: set(parents[name]) for name in nodes}
        conditioned_or_ancestors |= _reachable(node, reverse)
    for path in _simple_paths(nodes, edges, left, right):
        active = True
        for index in range(1, len(path) - 1):
            previous, middle, following = path[index - 1 : index + 2]
            collider = (previous, middle) in edges and (following, middle) in edges
            if collider:
                if middle not in conditioned_or_ancestors:
                    active = False
                    break
            elif middle in conditioned:
                active = False
                break
        if active:
            return False
    return True


def _valid_sets(nodes: tuple[str, ...], edges: set[Edge], query: dict[str, Any]) -> list[tuple[str, ...]]:
    treatment = query["treatment"]
    outcome = query["outcome"]
    paths = _directed_paths(nodes, edges, treatment, outcome)
    on_path = {node for path in paths for node in path[1:-1]}
    descendants = _reachable(treatment, _children(nodes, edges))
    forbidden = descendants - on_path - {outcome}
    candidates = tuple(
        node for node in query["candidate_variables"] if node not in forbidden
    )
    removed = {(left, right) for path in paths for left, right in zip(path, path[1:])}
    adjusted_edges = edges - removed
    result: list[tuple[str, ...]] = []
    for size in range(min(5, len(candidates)) + 1):
        for subset in combinations(candidates, size):
            if _d_separated_by_active_paths(
                nodes, adjusted_edges, treatment, outcome, set(subset)
            ):
                result.append(tuple(sorted(subset)))
                if len(result) == 100:
                    return result
    return result


def _ancestors_and_descendants(nodes: tuple[str, ...], edges: set[Edge], node: str) -> set[str]:
    parents = _parents(nodes, edges)
    return {node} | _reachable(node, _children(nodes, edges)) | _reachable(node, parents)


def _forbidden(nodes: tuple[str, ...], edges: set[Edge], query: dict[str, Any]) -> tuple[str, ...]:
    treatment = query["treatment"]
    outcome = query["outcome"]
    paths = _directed_paths(nodes, edges, treatment, outcome)
    on_path = {node for path in paths for node in path[1:-1]}
    forbidden_desc = _reachable(treatment, _children(nodes, edges)) - on_path - {outcome}
    relation_t = _ancestors_and_descendants(nodes, edges, treatment)
    relation_y = _ancestors_and_descendants(nodes, edges, outcome)
    colliders = {
        middle
        for left, middle, right in _colliders(nodes, edges)
        if middle not in {treatment, outcome}
        and ({left, right} & relation_t)
        and ({left, right} & relation_y)
    }
    return tuple(
        sorted((forbidden_desc | colliders) & set(query["candidate_variables"]))
    )


def _dag_answer(nodes: tuple[str, ...], edges: set[Edge], query: dict[str, Any]) -> tuple[Any, ...]:
    valid = _valid_sets(nodes, edges, query)
    task = query["task_id"]
    if task == TASKS[0]:
        return tuple(valid) if valid else ("no_backdoor",)
    if task == TASKS[1]:
        if not valid:
            return ("no_backdoor",)
        minimum = min(map(len, valid))
        return (tuple(item for item in valid if len(item) == minimum),)
    if task == TASKS[2]:
        return (min(map(len, valid)),) if valid else ("no_backdoor",)
    if task == TASKS[3]:
        return (len(valid),) if valid else ("no_backdoor",)
    if task == TASKS[4]:
        return (_forbidden(nodes, edges, query),) if valid else ("no_backdoor",)
    raise ValueError("Unknown conformance task")


def independent_target(row: dict[str, Any]) -> dict[str, Any]:
    """Compute the expected target without calling the production reasoner."""

    nodes = tuple(row["graph"]["nodes"])
    answers = [_dag_answer(nodes, edges, row["query"]) for edges in _compatible_dags(row["graph"])]
    if row["task_id"] == TASKS[0]:
        common = set(answers[0])
        for answer in answers[1:]:
            common &= set(answer)
        if common:
            accepted = sorted(common, key=repr)
            return {
                "status": "answered",
                "accepted": _jsonable(accepted),
                "compatible_dag_count": len(answers),
            }
    elif all(answer == answers[0] for answer in answers[1:]):
        return {
            "status": "answered",
            "accepted": _jsonable(list(answers[0])),
            "compatible_dag_count": len(answers),
        }
    return {
        "status": "undetermined",
        "accepted": ["undetermined"],
        "compatible_dag_count": len(answers),
    }


def independent_answer_class(row: dict[str, Any]) -> str:
    """Classify v3 cases using only the independent graph implementation."""

    target = independent_target(row)
    if target["status"] == "undetermined":
        return "undetermined"
    if target["accepted"] == ["no_backdoor"]:
        return "no_valid_adjustment_set"
    nodes = tuple(row["graph"]["nodes"])
    valid_families = [
        _valid_sets(nodes, edges, row["query"])
        for edges in _compatible_dags(row["graph"])
    ]
    empty_is_valid = [() in family for family in valid_families]
    if all(empty_is_valid):
        return "valid_empty_set"
    if not any(empty_is_valid):
        return "valid_nonempty_set"
    # Some task answers can remain invariant while empty-set validity changes.
    # V3 excludes this mixed class from its four registered answer strata.
    return "mixed_validity"


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def semantic_equivalent(
    *, task_id: str, parsed_status: str, parsed_answer: Any, expected: dict[str, Any]
) -> bool:
    """Narrow diagnostic equivalence; never replaces strict primary scoring."""

    if parsed_status == expected["status"]:
        if parsed_status == "undetermined":
            return parsed_answer == "undetermined"
        normalized = _jsonable(parsed_answer)
        if normalized in expected["accepted"]:
            return True
    no_set = expected["status"] == "answered" and expected["accepted"] == ["no_backdoor"]
    if no_set and task_id == TASKS[3] and parsed_status == "answered":
        return parsed_answer == 0
    if no_set and task_id == TASKS[1] and parsed_status == "answered":
        return parsed_answer == ()
    return False
