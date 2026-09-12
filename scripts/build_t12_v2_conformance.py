"""Build the deterministic, CausalDS-answer-free T12 v2 conformance suite."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.partial_graph import (  # noqa: E402
    PartialGraph,
    dag_to_cpdag_exact,
    unshielded_colliders,
)
from fourgraph.reasoner import (  # noqa: E402
    TASKS,
    TASK_FIELDS,
    ReasonerQuery,
    _all_directed_paths,
    _descendants,
    _forbidden_controls,
    _valid_adjustment_sets,
    conservative_target,
)
from fourgraph.reasoner_v2 import v2_query_view  # noqa: E402


OUTPUT = PROJECT_ROOT / "data/manifests/t12_v2_synthetic_conformance.jsonl"
AUDIT = PROJECT_ROOT / "data/manifests/t12_v2_synthetic_conformance_audit.json"
SEED = 1202
REQUIRED_TAGS = {
    "chain",
    "fork",
    "collider",
    "mediation",
    "confounding",
    "multiple_adjustment_sets",
    "empty_adjustment_set",
    "forbidden_descendant",
}
SCHEMAS = {
    TASKS[0]: "schemas/reasoner_one_valid_adjustment_set_v2.schema.json",
    TASKS[1]: "schemas/reasoner_all_minimal_adjustment_sets_v2.schema.json",
    TASKS[2]: "schemas/reasoner_minimal_adjustment_set_size_v2.schema.json",
    TASKS[3]: "schemas/reasoner_n_valid_adjustment_sets_v2.schema.json",
    TASKS[4]: "schemas/reasoner_forbidden_controls_list_v2.schema.json",
}


def _graph_view(graph: PartialGraph) -> dict[str, Any]:
    edges = [
        {"source": a, "target": b, "mark": "directed"}
        for a, b in sorted(graph.directed)
    ] + [
        {"source": a, "target": b, "mark": "undirected"}
        for a, b in sorted(graph.undirected)
    ]
    return {
        "schema_version": "fourgraph.reasoner_graph.v1",
        "graph_type": "cpdag" if graph.undirected else "dag",
        "nodes": list(graph.nodes),
        "edges": sorted(edges, key=lambda x: (x["source"], x["target"], x["mark"])),
    }


def _tags(dag: PartialGraph, query: ReasonerQuery) -> tuple[str, ...]:
    children = {node: set() for node in dag.nodes}
    parents = {node: set() for node in dag.nodes}
    for parent, child in dag.directed:
        children[parent].add(child)
        parents[child].add(parent)
    tags: set[str] = set()
    if any(children[node] and any(children[c] for c in children[node]) for node in dag.nodes):
        tags.add("chain")
    if any(len(children[node]) >= 2 for node in dag.nodes):
        tags.add("fork")
    if unshielded_colliders(dag):
        tags.add("collider")
    paths = _all_directed_paths(dag, query.treatment, query.outcome)
    if any(len(path) > 2 for path in paths):
        tags.add("mediation")
    ancestors_t = _ancestors(parents, query.treatment)
    ancestors_y = _ancestors(parents, query.outcome)
    if (ancestors_t & ancestors_y) - {query.treatment, query.outcome}:
        tags.add("confounding")
    valid = _valid_adjustment_sets(dag, query)
    if len(valid) > 1:
        tags.add("multiple_adjustment_sets")
    if () in valid:
        tags.add("empty_adjustment_set")
    descendants = _descendants(dag, query.treatment)
    on_path = {node for path in paths for node in path[1:-1]}
    if (descendants - on_path - {query.outcome}) & set(query.candidate_variables):
        tags.add("forbidden_descendant")
    if _forbidden_controls(dag, query):
        tags.add("forbidden_control")
    return tuple(sorted(tags))


def _ancestors(parents: dict[str, set[str]], node: str) -> set[str]:
    result = {node}
    stack = [node]
    while stack:
        for parent in parents[stack.pop()]:
            if parent not in result:
                result.add(parent)
                stack.append(parent)
    return result


def _candidate_pool() -> dict[tuple[str, str], list[dict[str, Any]]]:
    pools: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for task in TASKS:
        for bucket in ("dag_answered", "cpdag_answered", "cpdag_undetermined"):
            pools[(task, bucket)] = {}

    for n_nodes in (3, 4):
        nodes = tuple(f"X{i:03d}" for i in range(n_nodes))
        possible = tuple(combinations(nodes, 2))
        for mask in range(1 << len(possible)):
            directed = [edge for bit, edge in enumerate(possible) if mask & (1 << bit)]
            dag = PartialGraph.build(nodes, directed=directed)
            cpdag = dag_to_cpdag_exact(dag)
            for treatment in nodes:
                for outcome in nodes:
                    if treatment == outcome:
                        continue
                    candidates = tuple(node for node in nodes if node not in {treatment, outcome})
                    for task in TASKS:
                        query = ReasonerQuery(
                            "scene_900000",
                            task,
                            treatment,
                            outcome,
                            candidates,
                            TASK_FIELDS[task],
                        )
                        tags = _tags(dag, query)
                        for graph in (dag, cpdag):
                            view = _graph_view(graph)
                            target = conservative_target(graph, query)
                            mode = "cpdag" if view["graph_type"] == "cpdag" else "dag"
                            bucket = f"{mode}_{target.status}"
                            if bucket == "dag_undetermined":
                                continue
                            payload = {
                                "graph": view,
                                "query": v2_query_view(query),
                                "glossary": [
                                    {"id": node, "type": "continuous"} for node in nodes
                                ],
                                "expected": target.to_dict(),
                                "expected_response": {
                                    query.response_field: (
                                        "undetermined"
                                        if target.status == "undetermined"
                                        else target.accepted[0]
                                    )
                                },
                                "response_schema": SCHEMAS[task],
                                "feature_tags": list(tags),
                                "source_dag_sha256": sha256_hex(
                                    canonical_json_bytes(_graph_view(dag))
                                ),
                            }
                            identity = sha256_hex(canonical_json_bytes(payload))
                            pools[(task, bucket)][identity] = payload
    return {key: list(values.values()) for key, values in pools.items()}


def _select(pool: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(pool) < count:
        raise RuntimeError(f"Conformance pool too small: {len(pool)} < {count}")
    chosen: list[dict[str, Any]] = []
    tag_counts: Counter[str] = Counter()
    size_counts: Counter[int] = Counter()
    remaining = list(pool)
    while len(chosen) < count:
        def key(item: dict[str, Any]) -> tuple[Any, ...]:
            tags = item["feature_tags"]
            size = len(item["graph"]["nodes"])
            diversity = sum(tag_counts[tag] for tag in tags)
            digest = sha256_hex(
                f"{SEED}:".encode("ascii") + canonical_json_bytes(item)
            )
            return (diversity, size_counts[size], -len(tags), digest)

        item = min(remaining, key=key)
        remaining.remove(item)
        chosen.append(item)
        tag_counts.update(item["feature_tags"])
        size_counts[len(item["graph"]["nodes"])] += 1
    return chosen


def build() -> tuple[bytes, bytes]:
    pools = _candidate_pool()
    records: list[dict[str, Any]] = []
    quotas = {"dag_answered": 15, "cpdag_answered": 8, "cpdag_undetermined": 7}
    index = 0
    for task in TASKS:
        for bucket, count in quotas.items():
            for payload in _select(pools[(task, bucket)], count):
                index += 1
                records.append(
                    {
                        "schema_version": "fourgraph.synthetic_conformance_case.v1",
                        "case_id": f"SYN{index:03d}",
                        "task_id": task,
                        "bucket": bucket,
                        "uses_causalds_story": False,
                        "uses_causalds_answer": False,
                        **payload,
                    }
                )
    tags = Counter(tag for record in records for tag in record["feature_tags"])
    missing = REQUIRED_TAGS - set(tags)
    if missing:
        raise RuntimeError(f"Synthetic suite misses required features: {sorted(missing)}")
    payload = b"".join(canonical_json_bytes(record, newline=True) for record in records)
    buckets = Counter(record["bucket"] for record in records)
    task_counts = Counter(record["task_id"] for record in records)
    audit = {
        "schema_version": "fourgraph.synthetic_conformance_audit.v1",
        "cases": len(records),
        "seed": SEED,
        "generator": "exhaustive_four_node_dag_query_pool_diversity_selection_v1",
        "uses_causalds_story": False,
        "uses_causalds_answer": False,
        "task_counts": dict(sorted(task_counts.items())),
        "bucket_counts": dict(sorted(buckets.items())),
        "feature_counts": dict(sorted(tags.items())),
        "suite_sha256": sha256_hex(payload),
    }
    return payload, canonical_json_bytes(audit, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload, audit = build()
    if args.check:
        if OUTPUT.read_bytes() != payload or AUDIT.read_bytes() != audit:
            raise RuntimeError("Synthetic conformance artifacts do not reproduce byte-for-byte")
    else:
        OUTPUT.write_bytes(payload)
        AUDIT.write_bytes(audit)
    print(json.dumps(json.loads(audit), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
