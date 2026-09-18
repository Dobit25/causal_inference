from __future__ import annotations

import copy

import pytest

from fourgraph.edge_selective import (
    solve_edge_selective,
    validate_edge_selective_output,
)
from fourgraph.edge_selective_reference import reference_edge_selective
from fourgraph.hybrid_h2 import H2ContractError, PREFERENCE_SCHEMA, graph_sha256
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact


def fixture():
    dag = PartialGraph.build(
        ["X000", "X001", "X002", "X003"],
        [("X000", "X001"), ("X001", "X002"), ("X002", "X003")],
    )
    parent = dag_to_cpdag_exact(dag)
    artifact = {
        "schema_version": PREFERENCE_SCHEMA,
        "parent_graph_sha256": graph_sha256(parent),
        "preferences": [
            {"left": a, "right": b, "probability_left_causes_right": 0.999 if i == 0 else 0.5}
            for i, (a, b) in enumerate(sorted(parent.undirected))
        ],
    }
    return parent, artifact


def test_edge_selective_orients_supported_edge_and_propagates_meek_closure():
    parent, artifact = fixture()
    result = solve_edge_selective(parent, artifact, tau_semantic=0.99, tau_global=0.8)
    output = validate_edge_selective_output(parent, result)
    assert output.nodes == parent.nodes
    assert output.skeleton == parent.skeleton
    assert parent.directed.issubset(output.directed)
    assert result["direction_counts"]["semantic_selected"] >= 1
    assert result["direction_counts"]["closure_propagated"] >= 1


def test_production_and_independent_reference_agree():
    parent, artifact = fixture()
    production = solve_edge_selective(parent, artifact, tau_semantic=0.99, tau_global=0.8)
    reference = reference_edge_selective(parent, artifact, tau_semantic=0.99, tau_global=0.8)
    assert production["output_graph"] == reference["output_graph"]
    assert [(x["source"], x["target"]) for x in production["selected_directions"]] == [
        (x["source"], x["target"]) for x in reference["selected_directions"]
    ]


def test_ambiguous_evidence_preserves_undirected_edges():
    parent, artifact = fixture()
    for row in artifact["preferences"]:
        row["probability_left_causes_right"] = 0.5
    result = solve_edge_selective(parent, artifact, tau_semantic=0.8, tau_global=0.8)
    assert result["output_graph"] == parent.to_dict()
    assert result["direction_counts"]["unresolved"] == len(parent.undirected)


def test_invalid_threshold_and_corrupt_output_fail_closed():
    parent, artifact = fixture()
    with pytest.raises(H2ContractError, match="numeric"):
        solve_edge_selective(parent, artifact, tau_semantic=True, tau_global=0.8)
    result = solve_edge_selective(parent, artifact, tau_semantic=0.99, tau_global=0.8)
    corrupt = copy.deepcopy(result)
    corrupt["output_graph_sha256"] = "0" * 64
    with pytest.raises(H2ContractError, match="hash mismatch"):
        validate_edge_selective_output(parent, corrupt)


def test_exact_joint_selection_drops_one_direction_from_high_confidence_cycle():
    parent = PartialGraph.build(["A", "B", "C"], undirected=[("A", "B"), ("A", "C"), ("B", "C")])
    artifact = {
        "schema_version": PREFERENCE_SCHEMA,
        "parent_graph_sha256": graph_sha256(parent),
        "preferences": [
            {"left": "A", "right": "B", "probability_left_causes_right": 0.999},
            {"left": "A", "right": "C", "probability_left_causes_right": 0.001},
            {"left": "B", "right": "C", "probability_left_causes_right": 0.999},
        ],
    }
    result = solve_edge_selective(parent, artifact, tau_semantic=0.99, tau_global=0.5)
    assert len(result["candidate_directions"]) == 3
    assert len(result["selected_directions"]) == 2
    validate_edge_selective_output(parent, result)
