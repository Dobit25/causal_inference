"""Development-only construction helpers for the frozen P1 T21 protocol."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Mapping, Sequence

import numpy as np

from .graph_adapters import make_scd_graph_artifact
from .graph_contract import (
    EdgeAuditRecord,
    GraphArtifact,
    GraphProvenance,
    canonical_json_bytes,
    sha256_hex,
)
from .hybrid_h2 import graph_sha256
from .partial_graph import PartialGraph, unshielded_colliders


PREFERENCE_RESPONSE_SCHEMA = "fourgraph.p1_semantic_preferences_response.v1"
LLM_GRAPH_RESPONSE_SCHEMA = "fourgraph.p1_llm_graph_response.v1"


def render_preference_prompt(
    story: str,
    alias_by_node: Mapping[str, str],
    parent: PartialGraph,
    template: str,
) -> str:
    if set(alias_by_node) != set(parent.nodes):
        raise ValueError("Alias map and parent CPDAG have different node universes")
    requested = []
    for a, b in sorted(parent.undirected):
        left, right = sorted((alias_by_node[a], alias_by_node[b]))
        requested.append({"left": left, "right": right})
    if template.count("{{PAIRS_JSON}}") != 1 or template.count("{{STORY}}") != 1:
        raise ValueError("Preference prompt placeholders changed")
    return template.replace(
        "{{PAIRS_JSON}}", json.dumps(requested, ensure_ascii=False, indent=2, sort_keys=True)
    ).replace("{{STORY}}", story)


def parse_preference_response(
    raw_text: str,
    alias_by_node: Mapping[str, str],
    parent: PartialGraph,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    value = json.loads(raw_text)
    if not isinstance(value, dict) or set(value) != {"schema_version", "preferences"}:
        raise ValueError("Preference response has missing or unknown fields")
    if value["schema_version"] != PREFERENCE_RESPONSE_SCHEMA:
        raise ValueError("Preference response schema mismatch")
    rows = value["preferences"]
    if not isinstance(rows, list):
        raise ValueError("preferences must be an array")
    node_by_alias = {alias: node for node, alias in alias_by_node.items()}
    if len(node_by_alias) != len(alias_by_node):
        raise ValueError("Alias map is not one-to-one")
    expected_alias_pairs = {
        tuple(sorted((alias_by_node[a], alias_by_node[b]))) for a, b in parent.undirected
    }
    seen: set[tuple[str, str]] = set()
    canonical: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for row in rows:
        required = {"left", "right", "probability_left_causes_right", "evidence"}
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("Preference row has missing or unknown fields")
        left, right = row["left"], row["right"]
        if not isinstance(left, str) or not isinstance(right, str) or left >= right:
            raise ValueError("Public endpoints must preserve lexicographic order")
        if left not in node_by_alias or right not in node_by_alias:
            raise ValueError("Preference response used an unknown public name")
        pair = (left, right)
        if pair in seen:
            raise ValueError("Duplicate preference pair")
        seen.add(pair)
        probability = row["probability_left_causes_right"]
        if (
            isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or not math.isfinite(probability)
            or not 0.001 <= float(probability) <= 0.999
        ):
            raise ValueError("Preference probability outside [0.001, 0.999]")
        rationale = str(row["evidence"]).strip()
        if not rationale:
            raise ValueError("Preference evidence cannot be empty")
        a, b = node_by_alias[left], node_by_alias[right]
        canonical_left, canonical_right = sorted((a, b))
        canonical_probability = float(probability) if a == canonical_left else 1.0 - float(probability)
        canonical.append(
            {
                "left": canonical_left,
                "right": canonical_right,
                "probability_left_causes_right": canonical_probability,
            }
        )
        evidence.append(
            {
                "left": canonical_left,
                "right": canonical_right,
                "evidence": rationale,
            }
        )
    if seen != expected_alias_pairs:
        raise ValueError("Preference response does not cover exact unresolved edge set")
    artifact = {
        "schema_version": "fourgraph.semantic_preferences.v1",
        "parent_graph_sha256": graph_sha256(parent),
        "preferences": sorted(canonical, key=lambda item: (item["left"], item["right"])),
    }
    return artifact, tuple(sorted(evidence, key=lambda item: (item["left"], item["right"])))


def render_llm_graph_prompt(
    story: str, aliases: Sequence[str], template: str
) -> str:
    pairs = [
        {"left": left, "right": right}
        for left, right in combinations(sorted(map(str, aliases)), 2)
    ]
    if template.count("{{PAIRS_JSON}}") != 1 or template.count("{{STORY}}") != 1:
        raise ValueError("LLM graph prompt placeholders changed")
    return template.replace(
        "{{PAIRS_JSON}}", json.dumps(pairs, ensure_ascii=False, indent=2, sort_keys=True)
    ).replace("{{STORY}}", story)


def parse_llm_graph_response(
    raw_text: str, alias_by_node: Mapping[str, str]
) -> tuple[PartialGraph, tuple[dict[str, Any], ...]]:
    value = json.loads(raw_text)
    if not isinstance(value, dict) or set(value) != {"schema_version", "pair_decisions"}:
        raise ValueError("LLM graph response has missing or unknown fields")
    if value["schema_version"] != LLM_GRAPH_RESPONSE_SCHEMA:
        raise ValueError("LLM graph response schema mismatch")
    rows = value["pair_decisions"]
    if not isinstance(rows, list):
        raise ValueError("pair_decisions must be an array")
    node_by_alias = {alias: node for node, alias in alias_by_node.items()}
    aliases = tuple(sorted(node_by_alias))
    expected = set(combinations(aliases, 2))
    seen: set[tuple[str, str]] = set()
    directed: list[tuple[str, str]] = []
    audit: list[dict[str, Any]] = []
    for row in rows:
        required = {"left", "right", "relation", "confidence", "rationale"}
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("LLM graph row has missing or unknown fields")
        left, right = row["left"], row["right"]
        if not isinstance(left, str) or not isinstance(right, str) or left >= right:
            raise ValueError("LLM graph endpoints must preserve public lexicographic order")
        if (left, right) in seen or left not in node_by_alias or right not in node_by_alias:
            raise ValueError("Duplicate or unknown LLM graph pair")
        seen.add((left, right))
        relation = row["relation"]
        if relation not in {"left_causes_right", "right_causes_left", "no_direct_edge"}:
            raise ValueError("Unknown LLM graph relation")
        confidence = row["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= float(confidence) <= 1
        ):
            raise ValueError("Invalid LLM graph confidence")
        rationale = str(row["rationale"]).strip()
        if not rationale:
            raise ValueError("LLM graph rationale cannot be empty")
        if relation != "no_direct_edge":
            source_alias, target_alias = (
                (left, right) if relation == "left_causes_right" else (right, left)
            )
            directed.append((node_by_alias[source_alias], node_by_alias[target_alias]))
        audit.append(
            {
                "left": node_by_alias[left],
                "right": node_by_alias[right],
                "relation": relation,
                "confidence": float(confidence),
                "rationale": rationale,
            }
        )
    if seen != expected:
        raise ValueError("LLM graph response does not cover exact public pair set")
    return PartialGraph.build(sorted(alias_by_node), directed), tuple(audit)


def direct_lingam_graph(
    values: np.ndarray, nodes: Sequence[str], *, random_state: int, zero_tolerance: float
) -> tuple[PartialGraph, np.ndarray]:
    from lingam import DirectLiNGAM

    model = DirectLiNGAM(random_state=random_state)
    model.fit(np.asarray(values, dtype=np.float64))
    matrix = np.asarray(model.adjacency_matrix_, dtype=np.float64)
    if matrix.shape != (len(nodes), len(nodes)) or not np.isfinite(matrix).all():
        raise RuntimeError("DirectLiNGAM returned an invalid adjacency matrix")
    directed = [
        (str(nodes[source]), str(nodes[target]))
        for target in range(len(nodes))
        for source in range(len(nodes))
        if source != target and abs(float(matrix[target, source])) > zero_tolerance
    ]
    return PartialGraph.build(nodes, directed), matrix


def make_direct_lingam_artifact(
    *, scene_id: str, graph: PartialGraph, config_sha256: str, input_sha256: str, seed: int
) -> GraphArtifact:
    audit = [
        EdgeAuditRecord.build(
            step=step,
            source=source,
            target=target,
            action="add",
            before_mark="absent",
            after_mark="directed",
            actor="scd",
            reason="direct_lingam_nonzero_adjacency_coefficient",
            arbitrary=False,
        )
        for step, (source, target) in enumerate(sorted(graph.directed))
    ]
    return make_scd_graph_artifact(
        scene_id=scene_id,
        graph=graph,
        graph_type="dag",
        builder_id="fourgraph.p1_t21_direct_lingam",
        builder_version="v1",
        config_sha256=config_sha256,
        input_artifact_sha256=[input_sha256],
        seed=seed,
        edge_audit=audit,
    )


def make_semantic_graph_artifact(
    *,
    scene_id: str,
    parent: GraphArtifact | None,
    graph: PartialGraph,
    graph_method: str,
    graph_type: str,
    graph_view: str,
    builder_id: str,
    config_sha256: str,
    input_hashes: Sequence[str],
    edge_audit: Sequence[EdgeAuditRecord] = (),
) -> GraphArtifact:
    evidence = (
        ["public_story", "public_variable_semantics", "public_schema_types"]
        if graph_method == "llm"
        else ["parent_graph", "public_story", "public_variable_semantics", "public_schema_types"]
    )
    return GraphArtifact.from_partial_graph(
        graph,
        scene_id=scene_id,
        graph_method=graph_method,
        graph_type=graph_type,
        graph_view=graph_view,
        provenance=GraphProvenance.build(
            builder_id=builder_id,
            builder_version="v1",
            operation="learned" if graph_method == "llm" else "semantic_orientation",
            evidence_sources=evidence,
            config_sha256=config_sha256,
            input_artifact_sha256=input_hashes,
            parent_artifact_sha256=[] if parent is None else [parent.artifact_sha256],
            seed=None,
        ),
        edge_audit=edge_audit,
    )


def h1_local_orientation(
    parent: PartialGraph, preference_artifact: Mapping[str, Any]
) -> PartialGraph:
    from .hybrid_h2 import parse_preferences

    preferences = parse_preferences(parent, preference_artifact)
    directed = set(parent.directed)
    for item in preferences:
        directed.add(item.pair if item.probability_left_causes_right >= 0.5 else (item.right, item.left))
    graph = PartialGraph.build(parent.nodes, directed)
    if graph.skeleton != parent.skeleton or not parent.directed.issubset(graph.directed):
        raise ValueError("H1 changed parent skeleton or compelled direction")
    if unshielded_colliders(graph) != unshielded_colliders(parent):
        raise ValueError("H1 left the parent Markov equivalence class")
    return graph


def orientation_counts(
    output: PartialGraph, parent: PartialGraph, oracle: PartialGraph
) -> tuple[int, int]:
    correct = total = 0
    for left, right in parent.undirected:
        if (left, right) not in oracle.skeleton:
            continue
        if (left, right) in output.directed or (right, left) in output.directed:
            total += 1
            oracle_direction = (left, right) if (left, right) in oracle.directed else (right, left)
            correct += int(oracle_direction in output.directed)
    return correct, total


def select_threshold(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row["eligible"]]
    if not eligible:
        raise RuntimeError("No selective threshold meets frozen development gates")
    return min(
        eligible,
        key=lambda row: (
            -float(row["orientation_coverage"]),
            float(row["confident_wrong_rate"]),
            float(row["tau_margin"]),
            -float(row["tau_conflict"]),
        ),
    )


def content_sha256(value: Any) -> str:
    return sha256_hex(canonical_json_bytes(value))
