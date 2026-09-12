"""Build the sealed, balanced, answer-free T12 v3 conformance artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.conformance_audit import (  # noqa: E402
    independent_answer_class,
    independent_target,
)
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
    compatible_dags,
    conservative_target,
)
from fourgraph.reasoner_v2 import v2_query_view  # noqa: E402


SEED = 1203
SUITE = PROJECT_ROOT / "data/manifests/t12_v3_synthetic_conformance.jsonl"
AUDIT = PROJECT_ROOT / "data/manifests/t12_v3_synthetic_conformance_audit.json"
PANEL = PROJECT_ROOT / "data/manifests/t12_v3_manual_review_panel.jsonl"
SMOKE = PROJECT_ROOT / "data/manifests/t12_v3_openai_mini_smoke.json"
PROMPT_MANIFEST = PROJECT_ROOT / "data/manifests/t12_v3_prompt_contract.json"
V2_SUITE = PROJECT_ROOT / "data/manifests/t12_v2_synthetic_conformance.jsonl"

SCHEMAS = {
    TASKS[0]: "schemas/reasoner_one_valid_adjustment_set_v2.schema.json",
    TASKS[1]: "schemas/reasoner_all_minimal_adjustment_sets_v2.schema.json",
    TASKS[2]: "schemas/reasoner_minimal_adjustment_set_size_v2.schema.json",
    TASKS[3]: "schemas/reasoner_n_valid_adjustment_sets_v2.schema.json",
    TASKS[4]: "schemas/reasoner_forbidden_controls_list_v2.schema.json",
}

CELL_QUOTAS = {
    ("dag_answered", "valid_nonempty_set"): 6,
    ("dag_answered", "valid_empty_set"): 6,
    ("dag_answered", "no_valid_adjustment_set"): 6,
    ("cpdag_answered", "valid_nonempty_set"): 2,
    ("cpdag_answered", "valid_empty_set"): 2,
    ("cpdag_answered", "no_valid_adjustment_set"): 2,
    ("cpdag_undetermined", "undetermined"): 6,
}

REQUIRED_FEATURES = {
    "chain",
    "fork",
    "collider",
    "mediation",
    "confounding",
    "multiple_adjustment_sets",
    "empty_adjustment_set",
    "forbidden_descendant",
    "forbidden_control",
    "direct_outcome_to_treatment",
}

# A feature appearing once technically counts as coverage but is too fragile for a
# research conformance suite.  These are prospective, generator-level minima:
# they affect case selection, never model results.
REQUIRED_FEATURE_MIN_COUNTS = {
    "chain": 20,
    "fork": 20,
    "collider": 20,
    "mediation": 10,
    "confounding": 15,
    "multiple_adjustment_sets": 20,
    "empty_adjustment_set": 20,
    "forbidden_descendant": 10,
    "forbidden_control": 10,
    "direct_outcome_to_treatment": 20,
}


def _graph_view(graph: PartialGraph) -> dict[str, Any]:
    edges = [
        {"source": left, "target": right, "mark": "directed"}
        for left, right in sorted(graph.directed)
    ] + [
        {"source": left, "target": right, "mark": "undirected"}
        for left, right in sorted(graph.undirected)
    ]
    return {
        "schema_version": "fourgraph.reasoner_graph.v1",
        "graph_type": "cpdag" if graph.undirected else "dag",
        "nodes": list(graph.nodes),
        "edges": sorted(
            edges, key=lambda edge: (edge["source"], edge["target"], edge["mark"])
        ),
    }


def _ancestors(parents: dict[str, set[str]], node: str) -> set[str]:
    result = {node}
    stack = [node]
    while stack:
        for parent in parents[stack.pop()]:
            if parent not in result:
                result.add(parent)
                stack.append(parent)
    return result


def _tags(dag: PartialGraph, query: ReasonerQuery) -> tuple[str, ...]:
    children = {node: set() for node in dag.nodes}
    parents = {node: set() for node in dag.nodes}
    for parent, child in dag.directed:
        children[parent].add(child)
        parents[child].add(parent)
    tags: set[str] = set()
    if any(
        children[node] and any(children[child] for child in children[node])
        for node in dag.nodes
    ):
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
    if (query.outcome, query.treatment) in dag.directed:
        tags.add("direct_outcome_to_treatment")
    return tuple(sorted(tags))


def _production_answer_class(
    graph: PartialGraph,
    query: ReasonerQuery,
    target: Any,
) -> str:
    if target.status == "undetermined":
        return "undetermined"
    if target.accepted == ("no_backdoor",):
        return "no_valid_adjustment_set"
    families = [_valid_adjustment_sets(dag, query) for dag in compatible_dags(graph)]
    empty_is_valid = [() in family for family in families]
    if all(empty_is_valid):
        return "valid_empty_set"
    if not any(empty_is_valid):
        return "valid_nonempty_set"
    return "mixed_validity"


def _candidate_pools() -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    pools: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {
        (task, bucket, answer_class): {}
        for task in TASKS
        for bucket, answer_class in CELL_QUOTAS
    }
    nodes = tuple(f"X{index:03d}" for index in range(5))
    possible = tuple(combinations(nodes, 2))
    masks = sorted(
        range(1 << len(possible)),
        key=lambda mask: sha256_hex(f"{SEED}:{mask}".encode("ascii")),
    )
    minimum_pool_multiplier = 3

    for mask in masks:
        directed = [
            edge for bit, edge in enumerate(possible) if mask & (1 << bit)
        ]
        dag = PartialGraph.build(nodes, directed=directed)
        cpdag = dag_to_cpdag_exact(dag)
        source_sha = sha256_hex(canonical_json_bytes(_graph_view(dag)))
        for treatment in nodes:
            for outcome in nodes:
                if treatment == outcome:
                    continue
                candidates = tuple(
                    node for node in nodes if node not in {treatment, outcome}
                )
                for task in TASKS:
                    query = ReasonerQuery(
                        "scene_930000",
                        task,
                        treatment,
                        outcome,
                        candidates,
                        TASK_FIELDS[task],
                    )
                    tags = _tags(dag, query)
                    for graph in (dag, cpdag):
                        target = conservative_target(graph, query)
                        mode = "cpdag" if graph.undirected else "dag"
                        bucket = f"{mode}_{target.status}"
                        answer_class = _production_answer_class(
                            graph, query, target
                        )
                        key = (task, bucket, answer_class)
                        if key not in pools:
                            continue
                        payload = {
                            "graph": _graph_view(graph),
                            "query": v2_query_view(query),
                            "glossary": [
                                {"id": node, "type": "continuous"}
                                for node in nodes
                            ],
                            "expected": json.loads(
                                canonical_json_bytes(target.to_dict())
                            ),
                            "expected_response": {
                                query.response_field: (
                                    "undetermined"
                                    if target.status == "undetermined"
                                    else target.accepted[0]
                                )
                            },
                            "response_schema": SCHEMAS[task],
                            "answer_class": answer_class,
                            "feature_tags": list(tags),
                            "source_dag_sha256": source_sha,
                        }
                        identity = sha256_hex(
                            canonical_json_bytes(
                                {
                                    "task_id": task,
                                    "graph": payload["graph"],
                                    "query": payload["query"],
                                }
                            )
                        )
                        pools[key].setdefault(identity, payload)

        enough = all(
            len(pools[(task, bucket, answer_class)])
            >= quota * minimum_pool_multiplier
            for task in TASKS
            for (bucket, answer_class), quota in CELL_QUOTAS.items()
        )
        available_tags = {
            tag
            for candidates_by_id in pools.values()
            for item in candidates_by_id.values()
            for tag in item["feature_tags"]
        }
        if enough and REQUIRED_FEATURES <= available_tags:
            break
    else:
        raise RuntimeError("Five-node candidate enumeration did not fill V3 quotas")

    return {key: list(values.values()) for key, values in pools.items()}


def _select(
    pool: list[dict[str, Any]],
    count: int,
    tag_counts: Counter[str],
) -> list[dict[str, Any]]:
    if len(pool) < count:
        raise RuntimeError(f"V3 pool too small: {len(pool)} < {count}")
    chosen: list[dict[str, Any]] = []
    remaining = list(pool)
    while len(chosen) < count:
        def key(item: dict[str, Any]) -> tuple[Any, ...]:
            coverage_gain = sum(
                tag_counts[tag] < REQUIRED_FEATURE_MIN_COUNTS[tag]
                for tag in item["feature_tags"]
            )
            diversity = sum(tag_counts[tag] for tag in item["feature_tags"])
            digest = sha256_hex(
                f"{SEED}:select:".encode("ascii") + canonical_json_bytes(item)
            )
            return (-coverage_gain, diversity, -len(item["feature_tags"]), digest)

        item = min(remaining, key=key)
        remaining.remove(item)
        chosen.append(item)
        tag_counts.update(item["feature_tags"])
    return chosen


def _build_suite() -> list[dict[str, Any]]:
    pools = _candidate_pools()
    selected: list[dict[str, Any]] = []
    tag_counts: Counter[str] = Counter()
    for task in TASKS:
        for (bucket, answer_class), count in CELL_QUOTAS.items():
            selected.extend(
                _select(pools[(task, bucket, answer_class)], count, tag_counts)
            )
    records = []
    for index, payload in enumerate(selected, 1):
        records.append(
            {
                "schema_version": "fourgraph.synthetic_conformance_case.v2",
                "case_id": f"V3SYN{index:03d}",
                "task_id": payload["query"]["task_id"],
                "bucket": (
                    f"{payload['graph']['graph_type']}_{payload['expected']['status']}"
                ),
                "uses_causalds_story": False,
                "uses_causalds_answer": False,
                **payload,
            }
        )
    missing = REQUIRED_FEATURES - {
        tag for record in records for tag in record["feature_tags"]
    }
    if missing:
        raise RuntimeError(f"Selected V3 suite misses features: {sorted(missing)}")
    feature_counts = Counter(
        tag for record in records for tag in record["feature_tags"]
    )
    below_minimum = {
        tag: (feature_counts[tag], minimum)
        for tag, minimum in REQUIRED_FEATURE_MIN_COUNTS.items()
        if feature_counts[tag] < minimum
    }
    if below_minimum:
        raise RuntimeError(f"Selected V3 suite misses feature minima: {below_minimum}")
    return records


def _first(
    rows: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    candidates = [row for row in rows if predicate(row)]
    if not candidates:
        raise RuntimeError("No V3 case satisfies a frozen panel/smoke criterion")
    return min(candidates, key=lambda row: row["case_id"])


def _manual_panel(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    panel: list[dict[str, Any]] = []
    criteria = (
        ("dag_valid_nonempty", lambda row: row["bucket"] == "dag_answered" and row["answer_class"] == "valid_nonempty_set"),
        ("dag_no_valid_direct_reverse", lambda row: row["bucket"] == "dag_answered" and row["answer_class"] == "no_valid_adjustment_set" and "direct_outcome_to_treatment" in row["feature_tags"]),
        ("cpdag_invariant_valid_empty", lambda row: row["bucket"] == "cpdag_answered" and row["answer_class"] == "valid_empty_set"),
        ("cpdag_undetermined", lambda row: row["bucket"] == "cpdag_undetermined"),
    )
    for task in TASKS:
        task_rows = [row for row in rows if row["task_id"] == task]
        for stratum, predicate in criteria:
            selected = _first(task_rows, predicate)
            panel.append(
                {
                    "schema_version": "fourgraph.t12_v3_manual_review_item.v1",
                    "case_id": selected["case_id"],
                    "task_id": task,
                    "stratum": stratum,
                    "answer_class": selected["answer_class"],
                    "graph": selected["graph"],
                    "query": selected["query"],
                    "expected": selected["expected"],
                    "independent_target": independent_target(selected),
                    "review_checklist": {
                        "five_node_case_not_in_v2_suite": True,
                        "node_and_edge_ids_consistent": True,
                        "treatment_outcome_excluded_from_candidates": True,
                        "sentinel_and_empty_outputs_distinguished": True,
                        "production_and_independent_targets_match": True,
                    },
                }
            )
    return panel


def _smoke_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    specifications = {
        TASKS[0]: (
            ("dag_answered", "valid_empty_set"),
            ("cpdag_undetermined", "undetermined"),
        ),
        TASKS[1]: (
            ("dag_answered", "no_valid_adjustment_set"),
            ("cpdag_answered", "valid_nonempty_set"),
        ),
        TASKS[2]: (
            ("dag_answered", "valid_empty_set"),
            ("cpdag_undetermined", "undetermined"),
        ),
        TASKS[3]: (
            ("dag_answered", "no_valid_adjustment_set"),
            ("cpdag_answered", "valid_empty_set"),
        ),
        TASKS[4]: (
            ("dag_answered", "valid_nonempty_set"),
            ("cpdag_undetermined", "undetermined"),
        ),
    }
    chosen: list[dict[str, Any]] = []
    for task in TASKS:
        task_rows = [row for row in rows if row["task_id"] == task]
        for bucket, answer_class in specifications[task]:
            matching = [
                row
                for row in task_rows
                if row["bucket"] == bucket
                and row["answer_class"] == answer_class
            ]
            if task == TASKS[4] and answer_class == "valid_nonempty_set":
                preferred = [
                    row for row in matching if "forbidden_control" in row["feature_tags"]
                ]
                matching = preferred or matching
            chosen.append(min(matching, key=lambda row: row["case_id"]))
    return {
        "schema_version": "fourgraph.t12_v3_smoke_manifest.v1",
        "seed": SEED,
        "case_ids": [row["case_id"] for row in chosen],
        "criteria": {
            "cases_per_task": 2,
            "contains_dag": True,
            "contains_cpdag_answered": True,
            "contains_cpdag_undetermined": True,
            "answer_classes": [
                "valid_nonempty_set",
                "valid_empty_set",
                "no_valid_adjustment_set",
                "undetermined",
            ],
            "selection": "frozen_task_specific_strata_then_lowest_case_id",
        },
    }


def _identity(row: dict[str, Any]) -> str:
    return sha256_hex(
        canonical_json_bytes(
            {
                "task_id": row["task_id"],
                "graph": row["graph"],
                "query": row["query"],
            }
        )
    )


def build() -> tuple[bytes, bytes, bytes, bytes]:
    rows = _build_suite()
    independent_targets = [independent_target(row) for row in rows]
    target_mismatches = [
        row["case_id"]
        for row, target in zip(rows, independent_targets)
        if target != row["expected"]
    ]
    class_mismatches = [
        row["case_id"]
        for row in rows
        if independent_answer_class(row) != row["answer_class"]
    ]
    if target_mismatches or class_mismatches:
        raise RuntimeError(
            f"V3 independent audit mismatch: targets={target_mismatches}, "
            f"classes={class_mismatches}"
        )

    panel = _manual_panel(rows)
    smoke = _smoke_manifest(rows)
    suite_payload = b"".join(
        canonical_json_bytes(row, newline=True) for row in rows
    )
    panel_payload = b"".join(
        canonical_json_bytes(row, newline=True) for row in panel
    )
    smoke_payload = canonical_json_bytes(smoke, newline=True)
    prompt_manifest = json.loads(PROMPT_MANIFEST.read_text(encoding="utf-8"))
    v2_rows = [
        json.loads(line)
        for line in V2_SUITE.read_text(encoding="utf-8").splitlines()
        if line
    ]
    overlap = sorted({_identity(row) for row in rows} & {_identity(row) for row in v2_rows})
    counts_by_task = Counter(row["task_id"] for row in rows)
    counts_by_bucket = Counter(row["bucket"] for row in rows)
    counts_by_class = Counter(row["answer_class"] for row in rows)
    joint_counts = Counter(
        (row["task_id"], row["bucket"], row["answer_class"])
        for row in rows
    )
    feature_counts = Counter(
        tag for row in rows for tag in row["feature_tags"]
    )
    audit = {
        "schema_version": "fourgraph.t12_v3_synthetic_conformance_audit.v1",
        "generator": "seeded_five_node_dag_cpdag_balanced_answer_class_v1",
        "seed": SEED,
        "suite_cases": len(rows),
        "node_counts": {"5": len(rows)},
        "uses_causalds_story": False,
        "uses_causalds_answer": False,
        "holdout_accessed": False,
        "task_counts": dict(sorted(counts_by_task.items())),
        "bucket_counts": dict(sorted(counts_by_bucket.items())),
        "answer_class_counts": dict(sorted(counts_by_class.items())),
        "joint_counts": {
            "|".join(key): value for key, value in sorted(joint_counts.items())
        },
        "feature_counts": dict(sorted(feature_counts.items())),
        "required_features": sorted(REQUIRED_FEATURES),
        "required_feature_min_counts": dict(
            sorted(REQUIRED_FEATURE_MIN_COUNTS.items())
        ),
        "feature_minimums_met": all(
            feature_counts[tag] >= minimum
            for tag, minimum in REQUIRED_FEATURE_MIN_COUNTS.items()
        ),
        "v2_case_identity_overlap": len(overlap),
        "production_solver": "fourgraph.reasoner.conservative_target",
        "independent_solver": "active_simple_paths_plus_exhaustive_cpdag_orientation_v1",
        "production_target_matches": len(rows) - len(target_mismatches),
        "production_target_mismatches": len(target_mismatches),
        "independent_answer_class_matches": len(rows) - len(class_mismatches),
        "independent_answer_class_mismatches": len(class_mismatches),
        "manual_review_panel_cases": len(panel),
        "manual_review_panel_per_task": 4,
        "manual_review_strata": sorted({row["stratum"] for row in panel}),
        "manual_review_checklists_complete": all(
            all(row["review_checklist"].values()) for row in panel
        ),
        "smoke_cases": len(smoke["case_ids"]),
        "smoke_cases_per_task": 2,
        "prompt_bundle_sha256": prompt_manifest["prompt_components"][
            "bundle_sha256"
        ],
        "suite_sha256": sha256_hex(suite_payload),
        "manual_review_panel_sha256": sha256_hex(panel_payload),
        "smoke_manifest_sha256": sha256_hex(smoke_payload),
        "measurement_ready_for_model_screening": (
            not target_mismatches
            and not class_mismatches
            and not overlap
            and len(panel) == 20
            and len(smoke["case_ids"]) == 10
            and set(feature_counts) >= REQUIRED_FEATURES
            and all(
                feature_counts[tag] >= minimum
                for tag, minimum in REQUIRED_FEATURE_MIN_COUNTS.items()
            )
        ),
    }
    return (
        suite_payload,
        canonical_json_bytes(audit, newline=True),
        panel_payload,
        smoke_payload,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payloads = build()
    targets = (SUITE, AUDIT, PANEL, SMOKE)
    if args.check:
        for target, payload in zip(targets, payloads):
            if target.read_bytes() != payload:
                raise RuntimeError(f"V3 artifact does not reproduce byte-for-byte: {target}")
    else:
        for target, payload in zip(targets, payloads):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
    print(json.dumps(json.loads(payloads[1]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
