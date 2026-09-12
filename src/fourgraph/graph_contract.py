"""Canonical graph and node-universe contracts for every four-graph condition."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from fourgraph.partial_graph import (
    PartialGraph,
    consistent_extension_with_trace,
    dag_to_cpdag_exact,
    validate_cpdag,
)


GRAPH_SCHEMA_VERSION = "fourgraph.graph.v1"
STRUCTURE_SCHEMA_VERSION = "fourgraph.structure.v1"
REASONER_GRAPH_SCHEMA_VERSION = "fourgraph.reasoner_graph.v1"
VARIABLE_MAP_SCHEMA_VERSION = "fourgraph.variable_map.v1"

GRAPH_METHODS = frozenset({"llm", "scd", "hybrid", "oracle"})
GRAPH_TYPES = frozenset({"dag", "cpdag"})
GRAPH_VIEWS = frozenset({"dag", "cpdag", "projected_dag"})
EDGE_MARKS = frozenset({"directed", "undirected"})
VARIABLE_TYPES = frozenset(
    {"binary", "continuous", "categorical", "ordinal", "count"}
)
OPERATIONS = frozenset(
    {"learned", "loaded", "semantic_orientation", "consistent_extension"}
)
EVIDENCE_SOURCES = frozenset(
    {
        "public_story",
        "public_variable_semantics",
        "public_schema_types",
        "public_schema_mapping",
        "public_observational_data",
        "parent_graph",
        "grading_ground_truth",
    }
)
EVIDENCE_ALLOWLISTS = {
    "llm": frozenset(
        {"public_story", "public_variable_semantics", "public_schema_types"}
    ),
    "scd": frozenset(
        {"public_observational_data", "public_schema_types", "parent_graph"}
    ),
    "hybrid": frozenset(
        {
            "parent_graph",
            "public_story",
            "public_variable_semantics",
            "public_schema_types",
        }
    ),
    "oracle": frozenset({"grading_ground_truth", "public_schema_mapping"}),
}

_SCENE_ID = re.compile(r"^scene_[0-9]+$")
_NODE_ID = re.compile(r"^X[0-9]{3}$")
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")


def canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    """Serialize JSON with the frozen byte-level canonicalization policy."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _require_sha256(value: str | None, field: str) -> None:
    if value is not None and not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be an uppercase SHA-256 digest")


@dataclass(frozen=True, order=True)
class GraphEdge:
    source: str
    target: str
    mark: str

    @classmethod
    def build(cls, source: str, target: str, mark: str) -> "GraphEdge":
        source = str(source)
        target = str(target)
        mark = str(mark)
        if mark not in EDGE_MARKS:
            raise ValueError(f"Unsupported edge mark: {mark}")
        if source == target:
            raise ValueError("Self-loops are forbidden")
        if mark == "undirected" and target < source:
            source, target = target, source
        return cls(source, target, mark)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphEdge":
        if set(value) != {"source", "target", "mark"}:
            raise ValueError("Graph edge has missing or unknown fields")
        return cls.build(value["source"], value["target"], value["mark"])

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "mark": self.mark}


@dataclass(frozen=True)
class GraphProvenance:
    builder_id: str
    builder_version: str
    operation: str
    evidence_sources: tuple[str, ...]
    config_sha256: str | None = None
    input_artifact_sha256: tuple[str, ...] = ()
    parent_artifact_sha256: tuple[str, ...] = ()
    seed: int | None = None

    @classmethod
    def build(
        cls,
        *,
        builder_id: str,
        builder_version: str,
        operation: str,
        evidence_sources: Iterable[str],
        config_sha256: str | None = None,
        input_artifact_sha256: Iterable[str] = (),
        parent_artifact_sha256: Iterable[str] = (),
        seed: int | None = None,
    ) -> "GraphProvenance":
        provenance = cls(
            str(builder_id),
            str(builder_version),
            str(operation),
            tuple(sorted(set(map(str, evidence_sources)))),
            config_sha256,
            tuple(sorted(set(map(str, input_artifact_sha256)))),
            tuple(sorted(set(map(str, parent_artifact_sha256)))),
            seed,
        )
        provenance.validate()
        return provenance

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphProvenance":
        required = {
            "builder_id",
            "builder_version",
            "operation",
            "evidence_sources",
            "config_sha256",
            "input_artifact_sha256",
            "parent_artifact_sha256",
            "seed",
        }
        if set(value) != required:
            raise ValueError("Graph provenance has missing or unknown fields")
        return cls.build(**value)

    def validate(self) -> None:
        if not self.builder_id or not _SAFE_ID.fullmatch(self.builder_id):
            raise ValueError("builder_id must be a non-empty safe identifier")
        if not self.builder_version or not _SAFE_ID.fullmatch(self.builder_version):
            raise ValueError("builder_version must be a non-empty safe identifier")
        if self.operation not in OPERATIONS:
            raise ValueError(f"Unsupported graph operation: {self.operation}")
        unknown = set(self.evidence_sources) - EVIDENCE_SOURCES
        if unknown:
            raise ValueError(f"Unknown evidence sources: {sorted(unknown)}")
        _require_sha256(self.config_sha256, "config_sha256")
        for digest in self.input_artifact_sha256:
            _require_sha256(digest, "input_artifact_sha256")
        for digest in self.parent_artifact_sha256:
            _require_sha256(digest, "parent_artifact_sha256")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("seed must be an integer or null")

    def to_dict(self) -> dict[str, Any]:
        return {
            "builder_id": self.builder_id,
            "builder_version": self.builder_version,
            "operation": self.operation,
            "evidence_sources": list(self.evidence_sources),
            "config_sha256": self.config_sha256,
            "input_artifact_sha256": list(self.input_artifact_sha256),
            "parent_artifact_sha256": list(self.parent_artifact_sha256),
            "seed": self.seed,
        }


@dataclass(frozen=True)
class EdgeAuditRecord:
    step: int
    source: str
    target: str
    action: str
    before_mark: str
    after_mark: str
    actor: str
    reason: str
    arbitrary: bool
    confidence: float | None = None

    @classmethod
    def build(
        cls,
        *,
        step: int,
        source: str,
        target: str,
        action: str,
        before_mark: str,
        after_mark: str,
        actor: str,
        reason: str,
        arbitrary: bool,
        confidence: float | None = None,
    ) -> "EdgeAuditRecord":
        record = cls(
            step,
            str(source),
            str(target),
            str(action),
            str(before_mark),
            str(after_mark),
            str(actor),
            str(reason),
            arbitrary,
            confidence,
        )
        record.validate()
        return record

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EdgeAuditRecord":
        required = {
            "step",
            "source",
            "target",
            "action",
            "before_mark",
            "after_mark",
            "actor",
            "reason",
            "arbitrary",
            "confidence",
        }
        if set(value) != required:
            raise ValueError("Edge audit record has missing or unknown fields")
        return cls.build(**value)

    def validate(self) -> None:
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step < 0:
            raise ValueError("Edge audit step must be a non-negative integer")
        if self.source == self.target:
            raise ValueError("Edge audit cannot target a self-loop")
        if self.action not in {"orient", "preserve", "add", "delete", "reject"}:
            raise ValueError(f"Unsupported edge audit action: {self.action}")
        if self.before_mark not in {"absent", "directed", "undirected"}:
            raise ValueError("Unsupported before_mark")
        if self.after_mark not in {"absent", "directed", "undirected"}:
            raise ValueError("Unsupported after_mark")
        if self.actor not in {"projection", "llm", "scd", "hybrid", "oracle", "validator"}:
            raise ValueError(f"Unsupported edge audit actor: {self.actor}")
        if not self.reason:
            raise ValueError("Edge audit reason cannot be empty")
        if not isinstance(self.arbitrary, bool):
            raise ValueError("Edge audit arbitrary flag must be boolean")
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1
        ):
            raise ValueError("Edge audit confidence must be finite and in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "source": self.source,
            "target": self.target,
            "action": self.action,
            "before_mark": self.before_mark,
            "after_mark": self.after_mark,
            "actor": self.actor,
            "reason": self.reason,
            "arbitrary": self.arbitrary,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class VariableDescriptor:
    canonical_id: str
    public_name: str
    variable_type: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "VariableDescriptor":
        if set(value) != {"canonical_id", "public_name", "variable_type"}:
            raise ValueError("Variable descriptor has missing or unknown fields")
        return cls(
            str(value["canonical_id"]),
            str(value["public_name"]),
            str(value["variable_type"]),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "canonical_id": self.canonical_id,
            "public_name": self.public_name,
            "variable_type": self.variable_type,
        }


@dataclass(frozen=True)
class VariableMap:
    scene_id: str
    variables: tuple[VariableDescriptor, ...]

    @classmethod
    def build(
        cls, scene_id: str, public_variables: Iterable[tuple[str, str]]
    ) -> "VariableMap":
        variables = tuple(
            VariableDescriptor(f"X{index:03d}", str(name), str(variable_type))
            for index, (name, variable_type) in enumerate(public_variables)
        )
        mapping = cls(str(scene_id), variables)
        mapping.validate()
        return mapping

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "VariableMap":
        required = {"schema_version", "scene_id", "variables", "mapping_sha256"}
        if set(value) != required:
            raise ValueError("Variable map has missing or unknown fields")
        if value["schema_version"] != VARIABLE_MAP_SCHEMA_VERSION:
            raise ValueError("Unsupported variable-map schema version")
        mapping = cls(
            str(value["scene_id"]),
            tuple(VariableDescriptor.from_dict(item) for item in value["variables"]),
        )
        mapping.validate()
        if value["mapping_sha256"] != mapping.mapping_sha256:
            raise ValueError("Variable-map hash mismatch")
        return mapping

    def validate(self) -> None:
        if not _SCENE_ID.fullmatch(self.scene_id):
            raise ValueError(f"Invalid scene_id: {self.scene_id}")
        expected = [f"X{index:03d}" for index in range(len(self.variables))]
        actual = [variable.canonical_id for variable in self.variables]
        if actual != expected:
            raise ValueError("Canonical IDs must be contiguous X000... in schema order")
        names = [variable.public_name for variable in self.variables]
        if len(set(names)) != len(names) or any(not name for name in names):
            raise ValueError("Public variable names must be non-empty and unique")
        unknown = {
            variable.variable_type
            for variable in self.variables
            if variable.variable_type not in VARIABLE_TYPES
        }
        if unknown:
            raise ValueError(f"Unsupported variable types: {sorted(unknown)}")

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(variable.canonical_id for variable in self.variables)

    @property
    def mapping_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": VARIABLE_MAP_SCHEMA_VERSION,
            "scene_id": self.scene_id,
            "variables": [variable.to_dict() for variable in self.variables],
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "mapping_sha256": self.mapping_sha256}

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), newline=True)

    @classmethod
    def from_json_bytes(cls, value: bytes) -> "VariableMap":
        mapping = cls.from_dict(json.loads(value.decode("utf-8")))
        if value != mapping.to_json_bytes():
            raise ValueError("Variable-map bytes are not canonically serialized")
        return mapping

    @classmethod
    def load(cls, path: str | Path) -> "VariableMap":
        return cls.from_json_bytes(Path(path).read_bytes())

    def write(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_json_bytes())

    def scd_rename_map(self) -> dict[str, str]:
        """Adapter-only map; public names must not reach the SCD algorithm."""

        return {
            variable.public_name: variable.canonical_id
            for variable in self.variables
        }

    def scd_algorithm_view(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": variable.canonical_id,
                    "variable_type": variable.variable_type,
                }
                for variable in self.variables
            ]
        }

    def semantic_builder_view(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": variable.canonical_id,
                    "public_name": variable.public_name,
                    "variable_type": variable.variable_type,
                }
                for variable in self.variables
            ]
        }

    def reasoner_glossary(self) -> list[dict[str, str]]:
        """Return non-causal type metadata without public semantic labels."""

        return [
            {
                "id": variable.canonical_id,
                "type": variable.variable_type,
            }
            for variable in self.variables
        ]


@dataclass(frozen=True)
class GraphArtifact:
    scene_id: str
    graph_method: str
    graph_type: str
    graph_view: str
    nodes: tuple[str, ...]
    edges: tuple[GraphEdge, ...]
    provenance: GraphProvenance
    edge_audit: tuple[EdgeAuditRecord, ...] = ()

    @classmethod
    def build(
        cls,
        *,
        scene_id: str,
        graph_method: str,
        graph_type: str,
        graph_view: str,
        nodes: Iterable[str],
        edges: Iterable[GraphEdge | Mapping[str, Any]],
        provenance: GraphProvenance,
        edge_audit: Iterable[EdgeAuditRecord | Mapping[str, Any]] = (),
    ) -> "GraphArtifact":
        raw_nodes = tuple(map(str, nodes))
        if len(set(raw_nodes)) != len(raw_nodes):
            raise ValueError("Duplicate graph nodes")
        normalized_edges = tuple(
            sorted(
                edge if isinstance(edge, GraphEdge) else GraphEdge.from_dict(edge)
                for edge in edges
            )
        )
        normalized_audit = tuple(
            sorted(
                [
                    (
                        item
                        if isinstance(item, EdgeAuditRecord)
                        else EdgeAuditRecord.from_dict(item)
                    )
                    for item in edge_audit
                ],
                key=lambda item: (
                    item.step,
                    item.source,
                    item.target,
                    item.action,
                    item.actor,
                ),
            )
        )
        artifact = cls(
            str(scene_id),
            str(graph_method),
            str(graph_type),
            str(graph_view),
            tuple(sorted(raw_nodes)),
            normalized_edges,
            provenance,
            normalized_audit,
        )
        artifact.validate()
        return artifact

    @classmethod
    def from_partial_graph(
        cls,
        graph: PartialGraph,
        *,
        scene_id: str,
        graph_method: str,
        graph_type: str,
        graph_view: str,
        provenance: GraphProvenance,
        edge_audit: Iterable[EdgeAuditRecord] = (),
    ) -> "GraphArtifact":
        edges = [GraphEdge.build(a, b, "directed") for a, b in graph.directed]
        edges.extend(GraphEdge.build(a, b, "undirected") for a, b in graph.undirected)
        return cls.build(
            scene_id=scene_id,
            graph_method=graph_method,
            graph_type=graph_type,
            graph_view=graph_view,
            nodes=graph.nodes,
            edges=edges,
            provenance=provenance,
            edge_audit=edge_audit,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphArtifact":
        required = {
            "schema_version",
            "scene_id",
            "graph_method",
            "graph_type",
            "graph_view",
            "nodes",
            "edges",
            "provenance",
            "edge_audit",
            "graph_sha256",
            "artifact_sha256",
        }
        if set(value) != required:
            raise ValueError("Graph artifact has missing or unknown fields")
        if value["schema_version"] != GRAPH_SCHEMA_VERSION:
            raise ValueError("Unsupported graph schema version")
        artifact = cls.build(
            scene_id=value["scene_id"],
            graph_method=value["graph_method"],
            graph_type=value["graph_type"],
            graph_view=value["graph_view"],
            nodes=value["nodes"],
            edges=value["edges"],
            provenance=GraphProvenance.from_dict(value["provenance"]),
            edge_audit=value["edge_audit"],
        )
        if value["graph_sha256"] != artifact.graph_sha256:
            raise ValueError("Graph structure hash mismatch")
        if value["artifact_sha256"] != artifact.artifact_sha256:
            raise ValueError("Graph artifact hash mismatch")
        return artifact

    @classmethod
    def from_json_bytes(cls, value: bytes) -> "GraphArtifact":
        artifact = cls.from_dict(json.loads(value.decode("utf-8")))
        if value != artifact.to_json_bytes():
            raise ValueError("Graph artifact bytes are not canonically serialized")
        return artifact

    @classmethod
    def load(cls, path: str | Path) -> "GraphArtifact":
        return cls.from_json_bytes(Path(path).read_bytes())

    def validate(self) -> None:
        if not _SCENE_ID.fullmatch(self.scene_id):
            raise ValueError(f"Invalid scene_id: {self.scene_id}")
        if self.graph_method not in GRAPH_METHODS:
            raise ValueError(f"Unsupported graph method: {self.graph_method}")
        if self.graph_type not in GRAPH_TYPES:
            raise ValueError(f"Unsupported graph type: {self.graph_type}")
        if self.graph_view not in GRAPH_VIEWS:
            raise ValueError(f"Unsupported graph view: {self.graph_view}")
        expected_nodes = tuple(f"X{index:03d}" for index in range(len(self.nodes)))
        if not 1 <= len(self.nodes) <= 8:
            raise ValueError("Graph node count must be between 1 and 8")
        if self.nodes != expected_nodes or any(
            not _NODE_ID.fullmatch(node) for node in self.nodes
        ):
            raise ValueError("Nodes must be contiguous canonical IDs X000...")
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("Duplicate canonical edge records")
        partial = self.partial_graph
        if self.graph_type == "dag":
            if partial.undirected:
                raise ValueError("DAG artifacts cannot contain undirected edges")
        else:
            validate_cpdag(partial)

        expected_view_type = {
            "dag": "dag",
            "cpdag": "cpdag",
            "projected_dag": "dag",
        }[self.graph_view]
        if self.graph_type != expected_view_type:
            raise ValueError("graph_view and graph_type disagree")
        allowed_views = {
            "llm": {"dag"},
            "scd": {"cpdag", "projected_dag", "dag"},
            "hybrid": {"dag"},
            "oracle": {"dag"},
        }[self.graph_method]
        if self.graph_view not in allowed_views:
            raise ValueError("Graph method cannot emit this graph view")

        self.provenance.validate()
        if self.provenance.config_sha256 is None:
            raise ValueError("Every graph artifact must reference a config hash")
        disallowed = set(self.provenance.evidence_sources) - EVIDENCE_ALLOWLISTS[
            self.graph_method
        ]
        if disallowed:
            raise ValueError(
                f"Evidence leakage for {self.graph_method}: {sorted(disallowed)}"
            )
        required_evidence = {
            "llm": {"public_story", "public_variable_semantics"},
            "scd": (
                {"parent_graph"}
                if self.graph_view == "projected_dag"
                else {"public_observational_data", "public_schema_types"}
            ),
            "hybrid": {
                "parent_graph",
                "public_story",
                "public_variable_semantics",
            },
            "oracle": {"grading_ground_truth"},
        }[self.graph_method]
        missing_evidence = required_evidence - set(self.provenance.evidence_sources)
        if missing_evidence:
            raise ValueError(
                f"Missing required evidence attestation: {sorted(missing_evidence)}"
            )
        expected_operation = {
            "llm": "learned",
            "scd": (
                "consistent_extension"
                if self.graph_view == "projected_dag"
                else "learned"
            ),
            "hybrid": "semantic_orientation",
            "oracle": "loaded",
        }[self.graph_method]
        if self.provenance.operation != expected_operation:
            raise ValueError(
                f"{self.graph_method}/{self.graph_view} must record {expected_operation}"
            )
        if self.graph_view == "projected_dag":
            if len(self.provenance.parent_artifact_sha256) != 1:
                raise ValueError("Projected DAG must reference exactly one parent CPDAG")
            if any(
                record.action != "orient"
                or record.before_mark != "undirected"
                or record.after_mark != "directed"
                or record.actor != "projection"
                or not record.arbitrary
                for record in self.edge_audit
            ):
                raise ValueError("Projected-DAG edge audit is not projection-only")
        if self.graph_method == "hybrid":
            if len(self.provenance.parent_artifact_sha256) != 1:
                raise ValueError("Hybrid graph must reference exactly one SCD parent")
        elif self.graph_view != "projected_dag" and self.provenance.parent_artifact_sha256:
            raise ValueError("Only projected DAG and Hybrid may reference parent graphs")
        if self.graph_view != "projected_dag" and not self.provenance.input_artifact_sha256:
            raise ValueError("Source graph artifacts must reference at least one input hash")
        audit_steps = [record.step for record in self.edge_audit]
        if audit_steps != list(range(len(audit_steps))):
            raise ValueError("Edge audit steps must be unique and contiguous from zero")
        for record in self.edge_audit:
            record.validate()
            if record.source not in self.nodes or record.target not in self.nodes:
                raise ValueError("Edge audit references a node outside the universe")

    @property
    def partial_graph(self) -> PartialGraph:
        directed = [
            (edge.source, edge.target)
            for edge in self.edges
            if edge.mark == "directed"
        ]
        undirected = [
            (edge.source, edge.target)
            for edge in self.edges
            if edge.mark == "undirected"
        ]
        return PartialGraph.build(self.nodes, directed, undirected)

    def _structure_payload(self) -> dict[str, Any]:
        return {
            "schema_version": STRUCTURE_SCHEMA_VERSION,
            "nodes": list(self.nodes),
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @property
    def graph_sha256(self) -> str:
        """Hash only normalized structure, intentionally ignoring provenance."""

        return sha256_hex(canonical_json_bytes(self._structure_payload()))

    def _artifact_payload(self) -> dict[str, Any]:
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "scene_id": self.scene_id,
            "graph_method": self.graph_method,
            "graph_type": self.graph_type,
            "graph_view": self.graph_view,
            "nodes": list(self.nodes),
            "edges": [edge.to_dict() for edge in self.edges],
            "provenance": self.provenance.to_dict(),
            "edge_audit": [record.to_dict() for record in self.edge_audit],
            "graph_sha256": self.graph_sha256,
        }

    @property
    def artifact_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self._artifact_payload()))

    def to_dict(self) -> dict[str, Any]:
        return {**self._artifact_payload(), "artifact_sha256": self.artifact_sha256}

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict(), newline=True)

    def write(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_json_bytes())

    def reasoner_view(self) -> dict[str, Any]:
        """Return a provenance-blind structure payload for the fixed reasoner."""

        return {
            "schema_version": REASONER_GRAPH_SCHEMA_VERSION,
            "graph_type": self.graph_type,
            "nodes": list(self.nodes),
            "edges": [edge.to_dict() for edge in self.edges],
        }

    def reasoner_json_bytes(self) -> bytes:
        """Return the canonical, provenance-blind bytes embedded in a prompt."""

        return canonical_json_bytes(self.reasoner_view())

    def metrics_view(self) -> PartialGraph:
        return self.partial_graph


def project_cpdag_artifact(
    parent: GraphArtifact,
    *,
    config_sha256: str,
    builder_version: str = "v1",
) -> GraphArtifact:
    """Create the frozen sensitivity DAG plus a complete arbitrary-edge log."""

    if parent.graph_method != "scd" or parent.graph_type != "cpdag":
        raise ValueError("Only an SCD CPDAG can create the P0 projected-DAG view")
    dag, trace = consistent_extension_with_trace(parent.partial_graph)
    provenance = GraphProvenance.build(
        builder_id="fourgraph.consistent_extension",
        builder_version=builder_version,
        operation="consistent_extension",
        evidence_sources=["parent_graph"],
        config_sha256=config_sha256,
        parent_artifact_sha256=[parent.artifact_sha256],
    )
    audit = [
        EdgeAuditRecord.build(
            step=decision.step,
            source=decision.source,
            target=decision.target,
            action="orient",
            before_mark="undirected",
            after_mark="directed",
            actor="projection",
            reason=decision.reason,
            arbitrary=decision.arbitrary,
        )
        for decision in trace
    ]
    return GraphArtifact.from_partial_graph(
        dag,
        scene_id=parent.scene_id,
        graph_method="scd",
        graph_type="dag",
        graph_view="projected_dag",
        provenance=provenance,
        edge_audit=audit,
    )


def assert_same_node_universe(artifacts: Iterable[GraphArtifact]) -> tuple[str, ...]:
    artifacts = tuple(artifacts)
    if not artifacts:
        raise ValueError("At least one graph artifact is required")
    scene_ids = {artifact.scene_id for artifact in artifacts}
    node_sets = {artifact.nodes for artifact in artifacts}
    if len(scene_ids) != 1 or len(node_sets) != 1:
        raise ValueError("Graph artifacts do not share one scene/node universe")
    return artifacts[0].nodes


def _validate_cpdag_child_relationship(
    parent: GraphArtifact,
    child: GraphArtifact,
    *,
    expected_method: str,
) -> None:
    if parent.graph_method != "scd" or parent.graph_view != "cpdag":
        raise ValueError("Parent must be a raw SCD CPDAG")
    if child.graph_method != expected_method or child.graph_type != "dag":
        raise ValueError(f"Child must be a {expected_method} DAG")
    if child.scene_id != parent.scene_id or child.nodes != parent.nodes:
        raise ValueError("Parent and child do not share one scene/node universe")
    if child.provenance.parent_artifact_sha256 != (parent.artifact_sha256,):
        raise ValueError("Child parent hash does not match the supplied CPDAG")
    if child.partial_graph.skeleton != parent.partial_graph.skeleton:
        raise ValueError("Child changed the parent CPDAG skeleton")
    if not parent.partial_graph.directed.issubset(child.partial_graph.directed):
        raise ValueError("Child changed a compelled parent direction")
    if dag_to_cpdag_exact(child.partial_graph) != parent.partial_graph:
        raise ValueError("Child DAG is outside the parent CPDAG equivalence class")

    expected_pairs = set(parent.partial_graph.undirected)
    audit_pairs: list[tuple[str, str]] = []
    for record in child.edge_audit:
        if (
            record.action != "orient"
            or record.before_mark != "undirected"
            or record.after_mark != "directed"
        ):
            raise ValueError("Child edge audit contains a non-orientation decision")
        pair = tuple(sorted((record.source, record.target)))
        audit_pairs.append(pair)
        if (record.source, record.target) not in child.partial_graph.directed:
            raise ValueError("Child edge audit disagrees with the final DAG")
    if len(audit_pairs) != len(set(audit_pairs)) or set(audit_pairs) != expected_pairs:
        raise ValueError("Child must audit every unresolved parent edge exactly once")


def validate_projection_relationship(
    parent: GraphArtifact, child: GraphArtifact
) -> None:
    """Validate a serialized deterministic CPDAG-to-DAG sensitivity pair."""

    if child.graph_view != "projected_dag":
        raise ValueError("Projection child must use the projected_dag view")
    _validate_cpdag_child_relationship(parent, child, expected_method="scd")
    expected, trace = consistent_extension_with_trace(parent.partial_graph)
    if child.partial_graph != expected:
        raise ValueError("Projected DAG is not the frozen deterministic extension")
    expected_directions = [(item.source, item.target) for item in trace]
    actual_directions = [(item.source, item.target) for item in child.edge_audit]
    if actual_directions != expected_directions or any(
        not item.arbitrary or item.actor != "projection" for item in child.edge_audit
    ):
        raise ValueError("Projection audit does not match the deterministic trace")


def validate_hybrid_relationship(parent: GraphArtifact, child: GraphArtifact) -> None:
    """Validate the frozen H1 skeleton-plus-semantic-orientation relationship."""

    if child.graph_view != "dag":
        raise ValueError("Hybrid child must use the DAG view")
    _validate_cpdag_child_relationship(parent, child, expected_method="hybrid")
    if any(item.arbitrary or item.actor != "hybrid" for item in child.edge_audit):
        raise ValueError("Hybrid audit must record non-arbitrary semantic decisions")
