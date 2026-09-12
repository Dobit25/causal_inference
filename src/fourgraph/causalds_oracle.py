"""Grading-only CausalDS Oracle graph loader.

This module is the production boundary for ground-truth graph access. It never
returns the raw grading document or task-answer fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fourgraph.causalds_access import (
    GradingPurpose,
    resolve_grading_artifact,
)
from fourgraph.causalds_public import (
    load_causalds_variable_map,
    read_json_object,
    sha256_file,
)
from fourgraph.graph_adapters import make_oracle_graph_artifact
from fourgraph.graph_contract import GraphArtifact, VariableMap
from fourgraph.partial_graph import PartialGraph


@dataclass(frozen=True)
class OracleLoadResult:
    """Safe Oracle output plus opaque provenance hashes."""

    variable_map: VariableMap
    graph_artifact: GraphArtifact
    public_schema_sha256: str
    grading_ground_truth_sha256: str

    def audit_record(self) -> dict[str, Any]:
        """Return an edge-free record safe for versioned audit manifests."""

        return {
            "scene_id": self.graph_artifact.scene_id,
            "node_count": len(self.graph_artifact.nodes),
            "edge_count": len(self.graph_artifact.edges),
            "variable_mapping_sha256": self.variable_map.mapping_sha256,
            "public_schema_sha256": self.public_schema_sha256,
            "grading_ground_truth_sha256": self.grading_ground_truth_sha256,
            "graph_sha256": self.graph_artifact.graph_sha256,
            "graph_artifact_sha256": self.graph_artifact.artifact_sha256,
            "graph_type": self.graph_artifact.graph_type,
            "graph_view": self.graph_artifact.graph_view,
            "valid": True,
        }


def _load_oracle_partial_graph(
    source_root: Path,
    scene_id: str,
    variable_map: VariableMap,
) -> tuple[PartialGraph, str]:
    path = resolve_grading_artifact(
        source_root,
        scene_id,
        "ground_truth",
        purpose=GradingPurpose.ORACLE,
    )
    ground_truth = read_json_object(path, label="Grading ground truth")
    if ground_truth.get("scene_id") != scene_id:
        raise ValueError("Ground-truth scene_id does not match the requested scene")
    graph = ground_truth.get("graph")
    if not isinstance(graph, dict):
        raise ValueError("Ground truth does not contain a graph object")

    public_names = tuple(variable.public_name for variable in variable_map.variables)
    observed = graph.get("observed_nodes_named")
    latent = graph.get("latent_nodes_named")
    nodes = graph.get("nodes_named")
    if not isinstance(observed, list) or len(observed) != len(set(observed)):
        raise ValueError("Ground-truth observed node list is malformed")
    if not isinstance(latent, list):
        raise ValueError("Ground-truth latent node list is malformed")
    if latent:
        raise ValueError("P0 Oracle loader rejects scenes with latent nodes")
    if set(observed) != set(public_names):
        raise ValueError("Ground-truth observed nodes do not match public schema")
    if not isinstance(nodes, list) or set(nodes) != set(public_names):
        raise ValueError("Ground-truth graph nodes do not match public schema")

    mapping = ground_truth.get("mapping")
    if not isinstance(mapping, dict) or set(mapping.values()) != set(public_names):
        raise ValueError("Ground-truth public mapping does not match public schema")
    edges = graph.get("edges_named_observed")
    all_edges = graph.get("edges_named")
    if not isinstance(edges, list) or not isinstance(all_edges, list):
        raise ValueError("Ground-truth named edges are malformed")
    normalized_edges: list[tuple[str, str]] = []
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("Ground-truth edge must contain two endpoints")
        parent, child = edge
        if parent not in public_names or child not in public_names:
            raise ValueError("Ground-truth edge references an unknown public node")
        normalized_edges.append((parent, child))
    if {tuple(edge) for edge in all_edges} != set(normalized_edges):
        raise ValueError("Observed and full named edges disagree in no-latent scene")

    canonical = variable_map.scd_rename_map()
    dag = PartialGraph.build(
        variable_map.node_ids,
        directed=[
            (canonical[parent], canonical[child])
            for parent, child in normalized_edges
        ],
    )
    return dag, sha256_file(path)


def load_causalds_oracle_graph(
    source_root: Path,
    scene_id: str,
    *,
    config_sha256: str,
    builder_version: str = "v1",
    variant: str = "clean",
) -> OracleLoadResult:
    """Load one CausalDS grading DAG as the canonical Oracle artifact."""

    variable_map, schema_sha256 = load_causalds_variable_map(
        source_root, scene_id, variant=variant
    )
    dag, ground_truth_sha256 = _load_oracle_partial_graph(
        source_root, scene_id, variable_map
    )
    artifact = make_oracle_graph_artifact(
        scene_id=scene_id,
        graph=dag,
        builder_id="fourgraph.causalds_oracle",
        builder_version=builder_version,
        config_sha256=config_sha256,
        input_artifact_sha256=[schema_sha256, ground_truth_sha256],
    )
    return OracleLoadResult(
        variable_map=variable_map,
        graph_artifact=artifact,
        public_schema_sha256=schema_sha256,
        grading_ground_truth_sha256=ground_truth_sha256,
    )


def load_oracle_dag_for_dev_scoring(
    source_root: Path,
    scene_id: str,
    anonymous_names: tuple[str, ...],
) -> PartialGraph:
    """Compatibility helper for the frozen T05 development evaluator only."""

    variable_map, _ = load_causalds_variable_map(source_root, scene_id)
    if variable_map.node_ids != anonymous_names:
        raise ValueError("Oracle mapping does not match the anonymous node set")
    dag, _ = _load_oracle_partial_graph(source_root, scene_id, variable_map)
    return dag
