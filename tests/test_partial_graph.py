import pytest

from fourgraph.partial_graph import (
    PartialGraph,
    consistent_extension,
    cpdag_metrics,
    dag_to_cpdag_exact,
    graph_stability,
)


def test_exact_cpdag_distinguishes_chain_and_collider():
    chain = PartialGraph.build(
        ["A", "B", "C"], directed=[("A", "B"), ("B", "C")]
    )
    chain_cpdag = dag_to_cpdag_exact(chain)
    assert chain_cpdag.directed == frozenset()
    assert chain_cpdag.undirected == frozenset({("A", "B"), ("B", "C")})

    collider = PartialGraph.build(
        ["A", "B", "C"], directed=[("A", "B"), ("C", "B")]
    )
    collider_cpdag = dag_to_cpdag_exact(collider)
    assert collider_cpdag.directed == frozenset({("A", "B"), ("C", "B")})
    assert collider_cpdag.undirected == frozenset()


def test_consistent_extension_is_lexicographic_and_preserves_invariants():
    cpdag = PartialGraph.build(
        ["A", "B", "C"], undirected=[("A", "B"), ("B", "C")]
    )
    extension = consistent_extension(cpdag)
    assert extension.directed == frozenset({("B", "A"), ("C", "B")})
    assert extension.skeleton == cpdag.skeleton
    assert extension.is_directed_acyclic()


def test_consistent_extension_rejects_directed_cycle_at_contract_boundary():
    with pytest.raises(ValueError, match="cycle"):
        PartialGraph.build(
            ["A", "B", "C"],
            directed=[("A", "B"), ("B", "C"), ("C", "A")],
        )


def test_cpdag_metrics_penalize_extra_adjacency_and_overorientation():
    oracle = PartialGraph.build(
        ["A", "B", "C"], directed=[("A", "B"), ("B", "C")]
    )
    estimate = PartialGraph.build(
        ["A", "B", "C"],
        directed=[("A", "B")],
        undirected=[("B", "C"), ("A", "C")],
    )
    metrics = cpdag_metrics(estimate, oracle)
    assert metrics["skeleton_false_positive"] == 1
    assert metrics["compelled_orientation_precision"] == 0.0
    assert metrics["cpdag_shd"] == 2


def test_graph_stability_uses_skeleton_and_endpoint_states():
    left = PartialGraph.build(
        ["A", "B", "C"], undirected=[("A", "B"), ("B", "C")]
    )
    right = PartialGraph.build(
        ["A", "B", "C"],
        directed=[("A", "B")],
        undirected=[("B", "C")],
    )
    result = graph_stability(left, right)
    assert result["skeleton_jaccard"] == 1.0
    assert result["endpoint_state_agreement"] == pytest.approx(2 / 3)
