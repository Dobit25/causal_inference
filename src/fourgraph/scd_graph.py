"""T09 construction of canonical SCD CPDAG and projected-DAG artifacts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from fourgraph.causalds_scd import CandidateSpec, SceneData
from fourgraph.graph_adapters import make_scd_graph_artifact
from fourgraph.graph_contract import (
    EdgeAuditRecord,
    GraphArtifact,
    project_cpdag_artifact,
    validate_projection_relationship,
)
from fourgraph.partial_graph import PartialGraph


class SCDBackend(Protocol):
    def to_java_dataset(self, scene_data: SceneData) -> Any: ...

    def run(self, dataset: Any, spec: CandidateSpec) -> tuple[PartialGraph, float]: ...


@dataclass(frozen=True)
class SCDGraphPolicy:
    candidate_id: str
    family: str
    penalty_discount: float
    truncation_limit: int
    seed: int | None
    builder_version: str = "v1"

    def validate(self) -> None:
        if self.candidate_id != "boss_basis_bic__p1__t3":
            raise ValueError("T09 must use the T05-frozen candidate")
        if self.family != "boss_basis_bic":
            raise ValueError("T09 must use BOSS + BasisFunctionBicScore")
        if (
            isinstance(self.penalty_discount, bool)
            or not isinstance(self.penalty_discount, (int, float))
            or not math.isfinite(self.penalty_discount)
            or float(self.penalty_discount) != 1.0
        ):
            raise ValueError("T09 penalty_discount must remain 1.0")
        if self.truncation_limit != 3:
            raise ValueError("T09 truncation_limit must remain 3")
        if self.seed is not None:
            raise ValueError("T09 data-order BOSS does not claim a stochastic seed")
        if not self.builder_version:
            raise ValueError("T09 builder_version cannot be empty")

    def candidate(self) -> CandidateSpec:
        self.validate()
        return CandidateSpec(
            self.candidate_id,
            self.family,
            True,
            {
                "penalty_discount": float(self.penalty_discount),
                "truncation_limit": self.truncation_limit,
            },
        )


@dataclass(frozen=True)
class SCDGraphBuildResult:
    scene_id: str
    raw_cpdag: GraphArtifact
    projected_dag: GraphArtifact
    runtime_seconds: float

    def audit_record(self) -> dict[str, Any]:
        raw = self.raw_cpdag.partial_graph
        projected = self.projected_dag.partial_graph
        return {
            "scene_id": self.scene_id,
            "node_count": len(raw.nodes),
            "raw_directed_edge_count": len(raw.directed),
            "raw_undirected_edge_count": len(raw.undirected),
            "raw_adjacency_count": len(raw.skeleton),
            "raw_graph_sha256": self.raw_cpdag.graph_sha256,
            "raw_artifact_sha256": self.raw_cpdag.artifact_sha256,
            "projected_directed_edge_count": len(projected.directed),
            "projected_graph_sha256": self.projected_dag.graph_sha256,
            "projected_artifact_sha256": self.projected_dag.artifact_sha256,
            "projection_parent_sha256": self.projected_dag.provenance.parent_artifact_sha256[0],
            "projection_orientations_audited": len(self.projected_dag.edge_audit),
            "valid": True,
        }


def _scd_edge_audit(graph: PartialGraph) -> tuple[EdgeAuditRecord, ...]:
    records: list[EdgeAuditRecord] = []
    for source, target in sorted(graph.directed):
        records.append(
            EdgeAuditRecord.build(
                step=len(records),
                source=source,
                target=target,
                action="add",
                before_mark="absent",
                after_mark="directed",
                actor="scd",
                reason="t05_frozen_boss_basis_bic_cpdag_output",
                arbitrary=False,
            )
        )
    for left, right in sorted(graph.undirected):
        records.append(
            EdgeAuditRecord.build(
                step=len(records),
                source=left,
                target=right,
                action="add",
                before_mark="absent",
                after_mark="undirected",
                actor="scd",
                reason="t05_frozen_boss_basis_bic_cpdag_output",
                arbitrary=False,
            )
        )
    return tuple(records)


def build_scd_graphs(
    scene_data: SceneData,
    *,
    backend: SCDBackend,
    policy: SCDGraphPolicy,
    config_sha256: str,
    input_artifact_sha256: Iterable[str],
) -> SCDGraphBuildResult:
    """Build one raw CPDAG and its deterministic sensitivity projection."""

    candidate = policy.candidate()
    expected_nodes = tuple(f"X{index:03d}" for index in range(len(scene_data.anonymous_names)))
    if scene_data.anonymous_names != expected_nodes:
        raise ValueError("SCD scene data must use contiguous canonical node IDs")
    dataset = backend.to_java_dataset(scene_data)
    graph, runtime_seconds = backend.run(dataset, candidate)
    if graph.nodes != expected_nodes:
        raise ValueError("SCD backend changed the scene node universe")
    if not math.isfinite(runtime_seconds) or runtime_seconds < 0:
        raise ValueError("SCD runtime must be finite and non-negative")

    raw = make_scd_graph_artifact(
        scene_id=scene_data.scene_id,
        graph=graph,
        graph_type="cpdag",
        builder_id="fourgraph.t09_scd_graph_builder",
        builder_version=policy.builder_version,
        config_sha256=config_sha256,
        input_artifact_sha256=input_artifact_sha256,
        seed=policy.seed,
        edge_audit=_scd_edge_audit(graph),
    )
    projected = project_cpdag_artifact(
        raw,
        config_sha256=config_sha256,
        builder_version=policy.builder_version,
    )
    validate_projection_relationship(raw, projected)
    return SCDGraphBuildResult(
        scene_id=scene_data.scene_id,
        raw_cpdag=raw,
        projected_dag=projected,
        runtime_seconds=float(runtime_seconds),
    )
