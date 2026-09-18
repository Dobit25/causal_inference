from __future__ import annotations

import copy

import numpy as np
import pytest

from fourgraph.bootstrap_boss import (
    BootstrapBossContractError,
    BootstrapGraphRun,
    aggregate_bootstrap_graphs,
    build_stability_parent,
    derive_bootstrap_seed,
    iter_bootstrap_indices,
    standardize_bootstrap_sample,
    validate_bootstrap_aggregate,
)
from fourgraph.bootstrap_boss_reference import reference_counts, reference_parent_graph
from fourgraph.partial_graph import PartialGraph


HASH = "A" * 64


def runs_for_counts(*, undirected=0, forward=0, reverse=0, absent=0):
    assert undirected + forward + reverse + absent == 200
    nodes = ("A", "B", "C")
    empty = PartialGraph.build(nodes)
    line = PartialGraph.build(nodes, undirected=[("A", "B")])
    arrow = PartialGraph.build(nodes, directed=[("A", "B"), ("C", "B")])
    back = PartialGraph.build(nodes, directed=[("B", "A"), ("C", "A")])
    graphs = [line] * undirected + [arrow] * forward + [back] * reverse + [empty] * absent
    return nodes, [BootstrapGraphRun(i, graph) for i, graph in enumerate(graphs)]


def test_bootstrap_indices_are_deterministic_size_n_and_not_identical():
    first = list(iter_bootstrap_indices("SYN", repetitions=2))
    second = list(iter_bootstrap_indices("SYN", repetitions=2))
    assert derive_bootstrap_seed("SYN", 0) == derive_bootstrap_seed("SYN", 0)
    assert len(first[0][1]) == 2000
    assert np.array_equal(first[0][1], second[0][1])
    assert not np.array_equal(first[0][1], first[1][1])
    assert len(np.unique(first[0][1])) < 2000


def test_each_resample_is_standardized_independently():
    values = np.column_stack((np.arange(2000), np.arange(2000) ** 2)).astype(float)
    _, indices = next(iter_bootstrap_indices("SYN"))
    standardized = standardize_bootstrap_sample(values, indices)
    assert np.allclose(standardized.mean(axis=0), 0.0, atol=1e-12)
    assert np.allclose(standardized.std(axis=0), 1.0, atol=1e-12)


def test_aggregator_uses_all_runs_as_denominator_and_matches_reference():
    nodes, runs = runs_for_counts(undirected=10, forward=180, absent=10)
    aggregate = aggregate_bootstrap_graphs("SYN", nodes, reversed(runs))
    target = next(row for row in aggregate["edge_evidence"] if row["edge"] == ["A", "B"])
    assert target["rates"] == {
        "absent": 0.05,
        "undirected": 0.05,
        "A_to_B": 0.9,
        "B_to_A": 0.0,
        "adjacency_stability": 0.95,
    }
    assert target["conditional_direction_rates_diagnostic"]["A_to_B"] == pytest.approx(180 / 190)
    assert reference_counts(nodes, runs)[("A", "B")] == target["counts"]


def test_parent_thresholds_filter_weak_edges_and_downgrade_uncertain_direction():
    nodes, runs = runs_for_counts(undirected=90, forward=55, reverse=35, absent=20)
    aggregate = aggregate_bootstrap_graphs("SYN", nodes, runs)
    result = build_stability_parent(
        aggregate,
        tau_adjacency=0.80,
        tau_direction=0.80,
        config_sha256=HASH,
        observations_sha256=HASH,
        seed_manifest_sha256=HASH,
    )
    assert ["A", "B"] in result["parent_graph"]["undirected"]
    reference = reference_parent_graph(
        nodes,
        reference_counts(nodes, runs),
        tau_adjacency=0.80,
        tau_direction=0.80,
    )
    assert result["parent_graph"] == reference.to_dict()


def test_strong_direction_is_retained_and_invalid_inputs_fail_closed():
    nodes, runs = runs_for_counts(undirected=10, forward=180, absent=10)
    aggregate = aggregate_bootstrap_graphs("SYN", nodes, runs)
    result = build_stability_parent(
        aggregate,
        tau_adjacency=0.90,
        tau_direction=0.90,
        config_sha256=HASH,
        observations_sha256=HASH,
        seed_manifest_sha256=HASH,
    )
    assert ["A", "B"] in result["parent_graph"]["directed"]
    with pytest.raises(BootstrapBossContractError, match="exactly 200"):
        aggregate_bootstrap_graphs("SYN", nodes, runs[:-1])
    corrupt = copy.deepcopy(aggregate)
    corrupt["edge_evidence"][0]["counts"]["absent"] += 1
    with pytest.raises(BootstrapBossContractError, match="sum to 200"):
        validate_bootstrap_aggregate(corrupt)
    with pytest.raises(BootstrapBossContractError, match="outside frozen grid"):
        build_stability_parent(
            aggregate,
            tau_adjacency=0.75,
            tau_direction=0.90,
            config_sha256=HASH,
            observations_sha256=HASH,
            seed_manifest_sha256=HASH,
        )


def test_extendable_but_noncompleted_pdag_is_rejected_as_a_boss_run():
    nodes, runs = runs_for_counts(undirected=200)
    runs[-1] = BootstrapGraphRun(
        199,
        PartialGraph.build(
            nodes,
            directed=[("A", "B")],
            undirected=[("B", "C")],
        ),
    )
    with pytest.raises(BootstrapBossContractError, match="not a valid completed PDAG"):
        aggregate_bootstrap_graphs("SYN", nodes, runs)
