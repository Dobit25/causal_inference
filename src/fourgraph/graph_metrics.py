"""Frozen structural graph metrics for the T11 development evaluation."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

from fourgraph.graph_contract import GraphArtifact, assert_same_node_universe
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact


METRIC_SCHEMA_VERSION = "fourgraph.graph_metric_record.v1"


def _round(value: float) -> float:
    return round(value, 8)


def _precision(tp: int, fp: int, *, empty_truth_and_prediction: bool) -> float:
    if tp + fp:
        return tp / (tp + fp)
    return 1.0 if empty_truth_and_prediction else 0.0


def _recall(tp: int, fn: int) -> float:
    return tp / (tp + fn) if tp + fn else 1.0


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def skeleton_metrics(estimate: PartialGraph, oracle_dag: PartialGraph) -> dict[str, int | float]:
    if estimate.nodes != oracle_dag.nodes:
        raise ValueError("Skeleton metrics require identical ordered node universes")
    predicted = estimate.skeleton
    truth = oracle_dag.skeleton
    tp = len(predicted & truth)
    fp = len(predicted - truth)
    fn = len(truth - predicted)
    precision = _precision(tp, fp, empty_truth_and_prediction=not truth)
    recall = _recall(tp, fn)
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": _round(precision),
        "recall": _round(recall),
        "f1": _round(_f1(precision, recall)),
        "shd": fp + fn,
    }


def cpdag_metrics_frozen(estimate: PartialGraph, oracle_dag: PartialGraph) -> dict[str, int | float]:
    if estimate.nodes != oracle_dag.nodes:
        raise ValueError("CPDAG metrics require identical ordered node universes")
    if oracle_dag.undirected:
        raise ValueError("CPDAG oracle input must be a DAG")
    oracle_cpdag = dag_to_cpdag_exact(oracle_dag)
    correct = len(estimate.directed & oracle_cpdag.directed)
    incorrect = len(estimate.directed - oracle_cpdag.directed)
    missed = len(oracle_cpdag.directed - estimate.directed)
    precision = _precision(
        correct,
        incorrect,
        empty_truth_and_prediction=not oracle_cpdag.directed,
    )
    recall = _recall(correct, missed)
    pair_count = len(tuple(combinations(estimate.nodes, 2)))
    state_shd = sum(
        estimate.edge_state(left, right) != oracle_cpdag.edge_state(left, right)
        for left, right in combinations(estimate.nodes, 2)
    )
    unresolved = len(estimate.undirected)
    adjacency_count = len(estimate.skeleton)
    return {
        "oracle_compelled_count": len(oracle_cpdag.directed),
        "predicted_compelled_count": len(estimate.directed),
        "correct_compelled": correct,
        "incorrect_compelled": incorrect,
        "missed_compelled": missed,
        "compelled_precision": _round(precision),
        "compelled_recall": _round(recall),
        "unresolved_count": unresolved,
        "unresolved_rate": _round(unresolved / adjacency_count if adjacency_count else 0.0),
        "state_shd": state_shd,
        "normalized_state_shd": _round(state_shd / pair_count if pair_count else 0.0),
    }


def dag_metrics_frozen(estimate: PartialGraph, oracle_dag: PartialGraph) -> dict[str, int | float]:
    if estimate.nodes != oracle_dag.nodes:
        raise ValueError("DAG metrics require identical ordered node universes")
    if estimate.undirected or oracle_dag.undirected:
        raise ValueError("Directed metrics require two DAGs")
    tp = len(estimate.directed & oracle_dag.directed)
    fp = len(estimate.directed - oracle_dag.directed)
    fn = len(oracle_dag.directed - estimate.directed)
    precision = _precision(tp, fp, empty_truth_and_prediction=not oracle_dag.directed)
    recall = _recall(tp, fn)
    common_adjacencies = estimate.skeleton & oracle_dag.skeleton
    correctly_oriented = sum(
        (left, right) in estimate.directed and (left, right) in oracle_dag.directed
        or (right, left) in estimate.directed and (right, left) in oracle_dag.directed
        for left, right in common_adjacencies
    )
    orientation_accuracy = (
        correctly_oriented / len(common_adjacencies)
        if common_adjacencies
        else 1.0
    )
    state_shd = sum(
        estimate.edge_state(left, right) != oracle_dag.edge_state(left, right)
        for left, right in combinations(estimate.nodes, 2)
    )
    pair_count = len(tuple(combinations(estimate.nodes, 2)))
    return {
        "directed_true_positive": tp,
        "directed_false_positive": fp,
        "directed_false_negative": fn,
        "directed_precision": _round(precision),
        "directed_recall": _round(recall),
        "directed_f1": _round(_f1(precision, recall)),
        "correctly_oriented_common_adjacencies": correctly_oriented,
        "common_adjacency_count": len(common_adjacencies),
        "orientation_accuracy_on_common_adjacencies": _round(orientation_accuracy),
        "shd_reversal_cost_one": state_shd,
        "normalized_shd_by_possible_pairs": _round(state_shd / pair_count if pair_count else 0.0),
    }


def hybrid_attribution(
    raw_cpdag: GraphArtifact,
    projected_dag: GraphArtifact,
    hybrid_dag: GraphArtifact,
    oracle_dag: GraphArtifact,
) -> dict[str, int]:
    assert_same_node_universe((raw_cpdag, projected_dag, hybrid_dag, oracle_dag))
    raw = raw_cpdag.metrics_view()
    projected = projected_dag.metrics_view()
    hybrid = hybrid_dag.metrics_view()
    oracle = oracle_dag.metrics_view()
    if raw_cpdag.graph_type != "cpdag" or projected_dag.graph_type != "dag" or hybrid_dag.graph_type != "dag" or oracle_dag.graph_type != "dag":
        raise ValueError("Hybrid attribution received an incompatible graph type")
    if raw.skeleton != projected.skeleton or raw.skeleton != hybrid.skeleton:
        raise ValueError("Hybrid attribution requires a fixed SCD skeleton")

    result = {
        "inherited_skeleton_false_positive": len(raw.skeleton - oracle.skeleton),
        "inherited_skeleton_false_negative": len(oracle.skeleton - raw.skeleton),
        "inherited_compelled_correct": 0,
        "inherited_compelled_incorrect": 0,
        "unresolved_evaluable": 0,
        "unresolved_not_evaluable_false_adjacency": 0,
        "semantic_orientation_correct": 0,
        "semantic_orientation_incorrect": 0,
        "projection_orientation_correct": 0,
        "projection_orientation_incorrect": 0,
        "semantic_vs_projection_disagreement": 0,
        "semantic_better_than_projection": 0,
        "semantic_worse_than_projection": 0,
        "semantic_and_projection_both_correct": 0,
        "semantic_and_projection_both_incorrect": 0,
    }
    for source, target in raw.directed:
        if (source, target) in oracle.directed:
            result["inherited_compelled_correct"] += 1
        else:
            result["inherited_compelled_incorrect"] += 1

    for left, right in raw.undirected:
        if (left, right) not in oracle.skeleton:
            result["unresolved_not_evaluable_false_adjacency"] += 1
            continue
        result["unresolved_evaluable"] += 1
        oracle_direction = (left, right) if (left, right) in oracle.directed else (right, left)
        semantic_correct = oracle_direction in hybrid.directed
        projection_correct = oracle_direction in projected.directed
        result["semantic_orientation_correct" if semantic_correct else "semantic_orientation_incorrect"] += 1
        result["projection_orientation_correct" if projection_correct else "projection_orientation_incorrect"] += 1
        if hybrid.edge_state(left, right) != projected.edge_state(left, right):
            result["semantic_vs_projection_disagreement"] += 1
        if semantic_correct and projection_correct:
            result["semantic_and_projection_both_correct"] += 1
        elif semantic_correct:
            result["semantic_better_than_projection"] += 1
        elif projection_correct:
            result["semantic_worse_than_projection"] += 1
        else:
            result["semantic_and_projection_both_incorrect"] += 1
    return result


def evaluate_graph(
    artifact: GraphArtifact,
    oracle: GraphArtifact,
    *,
    condition: str,
    role: str,
    variable_mapping_sha256: str,
    hybrid_error_attribution: dict[str, int] | None = None,
) -> dict[str, Any]:
    assert_same_node_universe((artifact, oracle))
    if oracle.graph_method != "oracle" or oracle.graph_type != "dag":
        raise ValueError("Graph metrics require a canonical Oracle DAG")
    partial = artifact.metrics_view()
    truth = oracle.metrics_view()
    cpdag = cpdag_metrics_frozen(partial, truth) if artifact.graph_type == "cpdag" else None
    dag = dag_metrics_frozen(partial, truth) if artifact.graph_type == "dag" else None
    functional_reason = (
        "raw_cpdag_not_supported_by_a_pinned_validated_implementation"
        if artifact.graph_type == "cpdag"
        else "no_pinned_validated_sid_or_aid_implementation_in_t11"
    )
    return {
        "schema_version": METRIC_SCHEMA_VERSION,
        "scene_id": artifact.scene_id,
        "graph_condition": condition,
        "evaluation_role": role,
        "graph_method": artifact.graph_method,
        "graph_type": artifact.graph_type,
        "graph_view": artifact.graph_view,
        "graph_schema_version": "fourgraph.graph.v1",
        "variable_mapping_sha256": variable_mapping_sha256,
        "graph_sha256": artifact.graph_sha256,
        "graph_artifact_sha256": artifact.artifact_sha256,
        "oracle_graph_sha256": oracle.graph_sha256,
        "oracle_artifact_sha256": oracle.artifact_sha256,
        "node_count": len(artifact.nodes),
        "graph_valid": True,
        "node_set_consistent": True,
        "skeleton": skeleton_metrics(partial, truth),
        "cpdag": cpdag,
        "dag": dag,
        "functional": {
            "sid": {"status": "unavailable", "value": None, "reason": functional_reason},
            "aid": {"status": "unavailable", "value": None, "reason": functional_reason},
        },
        "hybrid_attribution": hybrid_error_attribution,
    }


def load_graph_artifact_jsonl(path: str | Path) -> dict[str, GraphArtifact]:
    """Load a canonical graph JSONL set and reject duplicate scenes."""

    artifacts: dict[str, GraphArtifact] = {}
    for line_number, line in enumerate(Path(path).read_bytes().splitlines(), start=1):
        if not line:
            continue
        artifact = GraphArtifact.from_json_bytes(line + b"\n")
        if artifact.scene_id in artifacts:
            raise ValueError(f"Duplicate graph scene at line {line_number}: {path}")
        artifacts[artifact.scene_id] = artifact
    return artifacts
