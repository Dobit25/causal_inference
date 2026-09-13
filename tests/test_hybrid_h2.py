import math

import pytest

from fourgraph.graph_contract import GraphArtifact, GraphProvenance
from fourgraph.h2_reference import reference_forced
from fourgraph.hybrid_h2 import (
    H2ContractError,
    PREFERENCE_SCHEMA,
    graph_sha256,
    parse_preferences,
    solve_h2_forced,
    solve_h2_selective,
)
from fourgraph.partial_graph import PartialGraph, dag_to_cpdag_exact, unshielded_colliders


def _chain_parent() -> PartialGraph:
    dag = PartialGraph.build(
        ["X000", "X001", "X002"],
        [("X000", "X001"), ("X001", "X002")],
    )
    return dag_to_cpdag_exact(dag)


def _artifact(parent: PartialGraph, probabilities: list[float]) -> dict:
    return {
        "schema_version": PREFERENCE_SCHEMA,
        "parent_graph_sha256": graph_sha256(parent),
        "preferences": [
            {"left": left, "right": right, "probability_left_causes_right": probability}
            for (left, right), probability in zip(sorted(parent.undirected), probabilities)
        ],
    }


def test_h2_forced_resolves_locally_invalid_collider_preferences_globally():
    parent = _chain_parent()
    artifact = _artifact(parent, [0.9, 0.1])  # local argmax is X000 -> X001 <- X002
    result = solve_h2_forced(parent, artifact)
    selected = PartialGraph.build(
        result["selected_graph"]["nodes"], result["selected_graph"]["directed"]
    )
    assert selected.skeleton == parent.skeleton
    assert unshielded_colliders(selected) == unshielded_colliders(parent)
    assert result["normalized_conflict_mass"] > 0
    assert len(result["overridden_edges"]) == 1


def test_h2_forced_tie_uses_lexicographic_canonical_edge_serialization():
    parent = _chain_parent()
    artifact = _artifact(parent, [0.5, 0.5])
    production = solve_h2_forced(parent, artifact)
    reference = reference_forced(parent, artifact)
    assert production["selected_graph"] == reference["selected_graph"]
    assert production["normalized_margin"] == 0.0
    assert production["selected_graph"]["directed"] == [
        ["X000", "X001"],
        ["X001", "X002"],
    ]


def test_h2_selective_accepts_exact_forced_and_abstains_to_exact_parent():
    parent = _chain_parent()
    artifact = _artifact(parent, [0.9, 0.9])
    forced = solve_h2_forced(parent, artifact)
    accepted = solve_h2_selective(parent, forced, tau_margin=0.0, tau_conflict=1.0)
    abstained = solve_h2_selective(parent, forced, tau_margin=10.0, tau_conflict=1.0)
    assert accepted["decision"] == "accept"
    assert accepted["output_graph"] == forced["selected_graph"]
    assert abstained["decision"] == "abstain"
    assert abstained["output_graph"] == parent.to_dict()
    assert abstained["abstention_semantics"] == "unchanged_raw_cpdag"


def test_h2_contract_rejects_missing_duplicate_and_nonfinite_preferences():
    parent = _chain_parent()
    base = _artifact(parent, [0.7, 0.7])
    missing = {**base, "preferences": base["preferences"][:1]}
    duplicate = {**base, "preferences": [base["preferences"][0], base["preferences"][0]]}
    nonfinite = {
        **base,
        "preferences": [
            {**row, "probability_left_causes_right": math.nan if index == 0 else row["probability_left_causes_right"]}
            for index, row in enumerate(base["preferences"])
        ],
    }
    for artifact, code in ((missing, "missing_edge"), (duplicate, "duplicate_edge"), (nonfinite, "probability_nonfinite")):
        with pytest.raises(H2ContractError) as error:
            parse_preferences(parent, artifact)
        assert error.value.code == code


def test_h2_rejects_extendable_but_incomplete_pdag():
    incomplete = PartialGraph.build(
        ["X000", "X001", "X002"],
        directed=[("X001", "X002")],
        undirected=[("X000", "X001")],
    )
    artifact = _artifact(incomplete, [0.5])
    with pytest.raises(H2ContractError) as error:
        solve_h2_forced(incomplete, artifact)
    assert error.value.code == "invalid_cpdag"


def test_h2_does_not_mutate_parent_or_preference_artifact():
    parent = _chain_parent()
    artifact = _artifact(parent, [0.7, 0.3])
    parent_before = parent.to_dict()
    rows_before = [dict(row) for row in artifact["preferences"]]
    solve_h2_forced(parent, artifact)
    assert parent.to_dict() == parent_before
    assert artifact["preferences"] == rows_before


def test_h2_parent_hash_is_exactly_the_t06_canonical_structure_hash():
    parent = _chain_parent()
    provenance = GraphProvenance.build(
        builder_id="test.scd",
        builder_version="1",
        operation="learned",
        evidence_sources=["public_observational_data", "public_schema_types"],
        config_sha256="A" * 64,
        input_artifact_sha256=["B" * 64],
    )
    artifact = GraphArtifact.from_partial_graph(
        parent,
        scene_id="scene_100000",
        graph_method="scd",
        graph_type="cpdag",
        graph_view="cpdag",
        provenance=provenance,
    )
    assert graph_sha256(parent) == artifact.graph_sha256
