import json

import pytest

from fourgraph.graph_contract import (
    GRAPH_SCHEMA_VERSION,
    EdgeAuditRecord,
    GraphArtifact,
    GraphEdge,
    GraphProvenance,
    VariableMap,
    assert_same_node_universe,
    project_cpdag_artifact,
    validate_projection_relationship,
)
from fourgraph.partial_graph import PartialGraph, validate_cpdag


SHA_A = "A" * 64
SHA_B = "B" * 64


def provenance(method: str, *, parent: bool = False) -> GraphProvenance:
    values = {
        "llm": {
            "operation": "learned",
            "evidence_sources": ["public_story", "public_variable_semantics"],
        },
        "scd": {
            "operation": "learned",
            "evidence_sources": [
                "public_observational_data",
                "public_schema_types",
            ],
        },
        "hybrid": {
            "operation": "semantic_orientation",
            "evidence_sources": [
                "parent_graph",
                "public_story",
                "public_variable_semantics",
            ],
        },
        "oracle": {
            "operation": "loaded",
            "evidence_sources": ["grading_ground_truth"],
        },
    }[method]
    return GraphProvenance.build(
        builder_id=f"test.{method}",
        builder_version="v1",
        config_sha256=SHA_A,
        input_artifact_sha256=[SHA_A],
        parent_artifact_sha256=[SHA_B] if parent else [],
        **values,
    )


def artifact(
    method: str,
    graph_type: str,
    graph_view: str,
    edges,
    *,
    parent: bool = False,
) -> GraphArtifact:
    return GraphArtifact.build(
        scene_id="scene_000001",
        graph_method=method,
        graph_type=graph_type,
        graph_view=graph_view,
        nodes=["X002", "X000", "X001"],
        edges=edges,
        provenance=provenance(method, parent=parent),
    )


def test_variable_map_freezes_schema_order_and_separates_views():
    mapping = VariableMap.build(
        "scene_000001",
        [("Rain", "binary"), ("Temperature", "continuous")],
    )
    assert mapping.node_ids == ("X000", "X001")
    assert mapping.scd_rename_map() == {"Rain": "X000", "Temperature": "X001"}
    assert "public_name" not in json.dumps(mapping.scd_algorithm_view())
    assert mapping.reasoner_glossary() == [
        {"id": "X000", "type": "binary"},
        {"id": "X001", "type": "continuous"},
    ]
    assert VariableMap.from_dict(mapping.to_dict()) == mapping


def test_all_four_methods_share_one_contract_and_node_universe():
    dag_edges = [
        GraphEdge.build("X000", "X001", "directed"),
        GraphEdge.build("X002", "X001", "directed"),
    ]
    llm = artifact("llm", "dag", "dag", dag_edges)
    scd = artifact(
        "scd",
        "cpdag",
        "cpdag",
        [
            GraphEdge.build("X000", "X001", "undirected"),
            GraphEdge.build("X001", "X002", "undirected"),
        ],
    )
    hybrid = artifact("hybrid", "dag", "dag", dag_edges, parent=True)
    oracle = artifact("oracle", "dag", "dag", dag_edges)
    assert assert_same_node_universe([llm, scd, hybrid, oracle]) == (
        "X000",
        "X001",
        "X002",
    )
    assert all(item.to_dict()["schema_version"] == GRAPH_SCHEMA_VERSION for item in [llm, scd, hybrid, oracle])


def test_reasoner_view_is_structural_and_provenance_blind():
    graph = artifact(
        "oracle",
        "dag",
        "dag",
        [GraphEdge.build("X000", "X001", "directed")],
    )
    view = graph.reasoner_view()
    serialized = json.dumps(view)
    for forbidden in ("oracle", "provenance", "scene_", "sha256", "builder"):
        assert forbidden not in serialized
    assert view["graph_type"] == "dag"


def test_structure_hash_ignores_provenance_but_artifact_hash_does_not():
    edges = [GraphEdge.build("X000", "X001", "directed")]
    llm = artifact("llm", "dag", "dag", edges)
    oracle = artifact("oracle", "dag", "dag", edges)
    assert llm.graph_sha256 == oracle.graph_sha256
    assert llm.artifact_sha256 != oracle.artifact_sha256


def test_serialization_is_canonical_and_round_trips():
    left = artifact(
        "llm",
        "dag",
        "dag",
        [
            GraphEdge.build("X002", "X001", "directed"),
            GraphEdge.build("X000", "X001", "directed"),
        ],
    )
    right = GraphArtifact.build(
        scene_id="scene_000001",
        graph_method="llm",
        graph_type="dag",
        graph_view="dag",
        nodes=["X001", "X002", "X000"],
        edges=list(reversed(left.edges)),
        provenance=provenance("llm"),
    )
    assert left.to_json_bytes() == right.to_json_bytes()
    assert GraphArtifact.from_json_bytes(left.to_json_bytes()) == left


def test_file_loader_rejects_semantically_equal_noncanonical_json():
    graph = artifact(
        "oracle",
        "dag",
        "dag",
        [GraphEdge.build("X000", "X001", "directed")],
    )
    pretty = (json.dumps(graph.to_dict(), indent=2) + "\n").encode("utf-8")
    with pytest.raises(ValueError, match="not canonically serialized"):
        GraphArtifact.from_json_bytes(pretty)
    with pytest.raises(ValueError, match="not canonically serialized"):
        GraphArtifact.from_json_bytes(graph.to_json_bytes().replace(b"\n", b"\r\n"))


def test_hash_tampering_and_unknown_fields_are_rejected():
    graph = artifact(
        "oracle",
        "dag",
        "dag",
        [GraphEdge.build("X000", "X001", "directed")],
    )
    record = graph.to_dict()
    record["graph_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="structure hash"):
        GraphArtifact.from_dict(record)
    record = graph.to_dict()
    record["unexpected"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        GraphArtifact.from_dict(record)


def test_graph_type_and_evidence_leakage_are_rejected():
    with pytest.raises(ValueError, match="DAG artifacts"):
        artifact(
            "llm",
            "dag",
            "dag",
            [GraphEdge.build("X000", "X001", "undirected")],
        )
    leaking = GraphProvenance.build(
        builder_id="test.scd",
        builder_version="v1",
        operation="learned",
        evidence_sources=[
            "public_observational_data",
            "public_schema_types",
            "grading_ground_truth",
        ],
        config_sha256=SHA_A,
        input_artifact_sha256=[SHA_A],
    )
    with pytest.raises(ValueError, match="Evidence leakage"):
        GraphArtifact.build(
            scene_id="scene_000001",
            graph_method="scd",
            graph_type="dag",
            graph_view="dag",
            nodes=["X000", "X001"],
            edges=[GraphEdge.build("X000", "X001", "directed")],
            provenance=leaking,
        )


def test_cpdag_validation_rejects_extendable_but_uncompleted_pdag():
    incomplete = PartialGraph.build(
        ["X000", "X001", "X002"],
        directed=[("X000", "X001")],
        undirected=[("X001", "X002")],
    )
    with pytest.raises(ValueError, match="not a completed PDAG"):
        validate_cpdag(incomplete)


def test_projection_preserves_contract_and_logs_every_arbitrary_orientation():
    parent = artifact(
        "scd",
        "cpdag",
        "cpdag",
        [
            GraphEdge.build("X001", "X002", "undirected"),
            GraphEdge.build("X000", "X001", "undirected"),
        ],
    )
    projected = project_cpdag_artifact(parent, config_sha256=SHA_A)
    assert projected.graph_method == "scd"
    assert projected.graph_type == "dag"
    assert projected.graph_view == "projected_dag"
    assert projected.partial_graph.skeleton == parent.partial_graph.skeleton
    assert projected.provenance.parent_artifact_sha256 == (
        parent.artifact_sha256,
    )
    assert len(projected.edge_audit) == len(parent.partial_graph.undirected)
    assert all(record.arbitrary for record in projected.edge_audit)
    validate_projection_relationship(parent, projected)


def test_projection_trace_has_one_contiguous_step_per_dense_edge():
    parent = artifact(
        "scd",
        "cpdag",
        "cpdag",
        [
            GraphEdge.build("X000", "X001", "undirected"),
            GraphEdge.build("X000", "X002", "undirected"),
            GraphEdge.build("X001", "X002", "undirected"),
        ],
    )
    projected = project_cpdag_artifact(parent, config_sha256=SHA_A)
    assert [item.step for item in projected.edge_audit] == [0, 1, 2]
    validate_projection_relationship(parent, projected)


def test_edge_audit_rejects_nonfinite_confidence():
    with pytest.raises(ValueError, match="confidence"):
        EdgeAuditRecord.build(
            step=0,
            source="X000",
            target="X001",
            action="orient",
            before_mark="undirected",
            after_mark="directed",
            actor="projection",
            reason="test",
            arbitrary=True,
            confidence=float("nan"),
        )
