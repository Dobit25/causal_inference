"""Source-specific adapters that all emit the same :class:`GraphArtifact`."""

from __future__ import annotations

from typing import Iterable

from fourgraph.graph_contract import (
    EdgeAuditRecord,
    GraphArtifact,
    GraphProvenance,
    validate_hybrid_relationship,
)
from fourgraph.partial_graph import PartialGraph


def make_llm_graph_artifact(
    *,
    scene_id: str,
    graph: PartialGraph,
    builder_id: str,
    builder_version: str,
    config_sha256: str,
    input_artifact_sha256: Iterable[str],
    seed: int | None,
    edge_audit: Iterable[EdgeAuditRecord] = (),
) -> GraphArtifact:
    return GraphArtifact.from_partial_graph(
        graph,
        scene_id=scene_id,
        graph_method="llm",
        graph_type="dag",
        graph_view="dag",
        provenance=GraphProvenance.build(
            builder_id=builder_id,
            builder_version=builder_version,
            operation="learned",
            evidence_sources=[
                "public_story",
                "public_variable_semantics",
                "public_schema_types",
            ],
            config_sha256=config_sha256,
            input_artifact_sha256=input_artifact_sha256,
            seed=seed,
        ),
        edge_audit=edge_audit,
    )


def make_scd_graph_artifact(
    *,
    scene_id: str,
    graph: PartialGraph,
    graph_type: str,
    builder_id: str,
    builder_version: str,
    config_sha256: str,
    input_artifact_sha256: Iterable[str],
    seed: int | None,
    edge_audit: Iterable[EdgeAuditRecord] = (),
) -> GraphArtifact:
    if graph_type not in {"dag", "cpdag"}:
        raise ValueError("SCD graph_type must be dag or cpdag")
    return GraphArtifact.from_partial_graph(
        graph,
        scene_id=scene_id,
        graph_method="scd",
        graph_type=graph_type,
        graph_view=graph_type,
        provenance=GraphProvenance.build(
            builder_id=builder_id,
            builder_version=builder_version,
            operation="learned",
            evidence_sources=[
                "public_observational_data",
                "public_schema_types",
            ],
            config_sha256=config_sha256,
            input_artifact_sha256=input_artifact_sha256,
            seed=seed,
        ),
        edge_audit=edge_audit,
    )


def make_hybrid_graph_artifact(
    *,
    parent_scd: GraphArtifact,
    graph: PartialGraph,
    builder_id: str,
    builder_version: str,
    config_sha256: str,
    input_artifact_sha256: Iterable[str],
    seed: int | None,
    edge_audit: Iterable[EdgeAuditRecord],
) -> GraphArtifact:
    if parent_scd.graph_method != "scd" or parent_scd.graph_type != "cpdag":
        raise ValueError("Hybrid parent must be the raw SCD CPDAG")
    if graph.undirected:
        raise ValueError("The frozen H1 output must be a DAG")
    if graph.nodes != parent_scd.nodes:
        raise ValueError("Hybrid changed the node universe")
    if graph.skeleton != parent_scd.partial_graph.skeleton:
        raise ValueError("Hybrid changed the SCD skeleton")
    if not parent_scd.partial_graph.directed.issubset(graph.directed):
        raise ValueError("Hybrid changed a compelled SCD direction")
    audit = tuple(edge_audit)
    expected_pairs = parent_scd.partial_graph.undirected
    audited_pairs = {
        tuple(sorted((record.source, record.target)))
        for record in audit
        if record.action == "orient" and record.after_mark == "directed"
    }
    if audited_pairs != set(expected_pairs):
        raise ValueError("Hybrid must audit every unresolved SCD edge exactly by pair")
    if any(
        record.actor != "hybrid"
        or record.before_mark != "undirected"
        or record.after_mark != "directed"
        or record.arbitrary
        for record in audit
    ):
        raise ValueError("Hybrid orientation audit violates the H1 contract")

    artifact = GraphArtifact.from_partial_graph(
        graph,
        scene_id=parent_scd.scene_id,
        graph_method="hybrid",
        graph_type="dag",
        graph_view="dag",
        provenance=GraphProvenance.build(
            builder_id=builder_id,
            builder_version=builder_version,
            operation="semantic_orientation",
            evidence_sources=[
                "parent_graph",
                "public_story",
                "public_variable_semantics",
                "public_schema_types",
            ],
            config_sha256=config_sha256,
            input_artifact_sha256=input_artifact_sha256,
            parent_artifact_sha256=[parent_scd.artifact_sha256],
            seed=seed,
        ),
        edge_audit=audit,
    )
    validate_hybrid_relationship(parent_scd, artifact)
    return artifact


def make_oracle_graph_artifact(
    *,
    scene_id: str,
    graph: PartialGraph,
    builder_id: str,
    builder_version: str,
    config_sha256: str,
    input_artifact_sha256: Iterable[str],
) -> GraphArtifact:
    return GraphArtifact.from_partial_graph(
        graph,
        scene_id=scene_id,
        graph_method="oracle",
        graph_type="dag",
        graph_view="dag",
        provenance=GraphProvenance.build(
            builder_id=builder_id,
            builder_version=builder_version,
            operation="loaded",
            evidence_sources=["grading_ground_truth", "public_schema_mapping"],
            config_sha256=config_sha256,
            input_artifact_sha256=input_artifact_sha256,
        ),
    )
