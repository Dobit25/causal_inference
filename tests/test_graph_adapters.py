import pytest

from fourgraph.graph_adapters import (
    make_hybrid_graph_artifact,
    make_llm_graph_artifact,
    make_oracle_graph_artifact,
    make_scd_graph_artifact,
)
from fourgraph.graph_contract import EdgeAuditRecord, assert_same_node_universe
from fourgraph.partial_graph import PartialGraph


SHA = "A" * 64


def test_all_source_adapters_emit_one_artifact_type():
    dag = PartialGraph.build(
        ["X000", "X001", "X002"],
        directed=[("X000", "X001"), ("X002", "X001")],
    )
    cpdag = PartialGraph.build(
        ["X000", "X001", "X002"],
        directed=[("X000", "X001"), ("X002", "X001")],
    )
    common = {
        "scene_id": "scene_000001",
        "builder_version": "v1",
        "config_sha256": SHA,
        "input_artifact_sha256": [SHA],
    }
    llm = make_llm_graph_artifact(
        graph=dag, builder_id="test.llm", seed=42, **common
    )
    scd = make_scd_graph_artifact(
        graph=cpdag,
        graph_type="cpdag",
        builder_id="test.scd",
        seed=42,
        **common,
    )
    oracle = make_oracle_graph_artifact(
        graph=dag,
        builder_id="test.oracle",
        **{key: value for key, value in common.items() if key != "scene_id"},
        scene_id="scene_000001",
    )
    assert assert_same_node_universe([llm, scd, oracle]) == dag.nodes
    assert {item.graph_method for item in [llm, scd, oracle]} == {
        "llm",
        "scd",
        "oracle",
    }


def test_hybrid_adapter_preserves_parent_equivalence_class_and_audits_edges():
    parent_graph = PartialGraph.build(
        ["X000", "X001", "X002"],
        undirected=[("X000", "X001"), ("X001", "X002")],
    )
    parent = make_scd_graph_artifact(
        scene_id="scene_000001",
        graph=parent_graph,
        graph_type="cpdag",
        builder_id="test.scd",
        builder_version="v1",
        config_sha256=SHA,
        input_artifact_sha256=[SHA],
        seed=42,
    )
    hybrid_dag = PartialGraph.build(
        parent_graph.nodes,
        directed=[("X002", "X001"), ("X001", "X000")],
    )
    audit = [
        EdgeAuditRecord.build(
            step=index,
            source=source,
            target=target,
            action="orient",
            before_mark="undirected",
            after_mark="directed",
            actor="hybrid",
            reason="story_semantics",
            arbitrary=False,
            confidence=0.9,
        )
        for index, (source, target) in enumerate(sorted(hybrid_dag.directed))
    ]
    hybrid = make_hybrid_graph_artifact(
        parent_scd=parent,
        graph=hybrid_dag,
        builder_id="test.hybrid",
        builder_version="v1",
        config_sha256=SHA,
        input_artifact_sha256=[SHA],
        seed=42,
        edge_audit=audit,
    )
    assert hybrid.graph_method == "hybrid"
    assert hybrid.provenance.parent_artifact_sha256 == (
        parent.artifact_sha256,
    )


def test_hybrid_adapter_rejects_skeleton_repair():
    parent = make_scd_graph_artifact(
        scene_id="scene_000001",
        graph=PartialGraph.build(
            ["X000", "X001", "X002"],
            undirected=[("X000", "X001"), ("X001", "X002")],
        ),
        graph_type="cpdag",
        builder_id="test.scd",
        builder_version="v1",
        config_sha256=SHA,
        input_artifact_sha256=[SHA],
        seed=42,
    )
    repaired = PartialGraph.build(
        parent.nodes,
        directed=[("X000", "X002"), ("X002", "X001")],
    )
    with pytest.raises(ValueError, match="skeleton"):
        make_hybrid_graph_artifact(
            parent_scd=parent,
            graph=repaired,
            builder_id="test.hybrid",
            builder_version="v1",
            config_sha256=SHA,
            input_artifact_sha256=[SHA],
            seed=42,
            edge_audit=[],
        )
