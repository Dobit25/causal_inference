"""Deterministic, model-free semantic-story construction for P1 T19."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .p1_generation import seed64, stable_rank


CANONICAL_ID = re.compile(r"\bX[0-9]{3}\b")
DIRECTIONAL_CLAUSE = re.compile(
    r"^Within this process, changes in (?P<source>.+?) directly influence (?P<target>.+?)\.$"
)
SYMMETRIC_CLAUSE = re.compile(
    r"^(?P<left>.+?) and (?P<right>.+?) are directly connected in the process, "
    r"but this description does not establish which one influences the other\.$"
)
VARIANTS = ("full", "partial", "ambiguous")


@dataclass(frozen=True)
class StoryBundle:
    study_id: str
    scene_id: str
    alias_map: tuple[tuple[str, str], ...]
    clause_order: tuple[tuple[str, str], ...]
    partial_directional_edges: tuple[tuple[str, str], ...]
    public_records: tuple[dict[str, Any], ...]
    truth_record: dict[str, Any]


def assign_aliases(
    canonical_nodes: Sequence[str], lexicon: Sequence[str], master_seed: int, study_id: str
) -> tuple[tuple[str, str], ...]:
    """Assign neutral aliases using no graph feature or edge information."""
    if len(canonical_nodes) > len(lexicon):
        raise ValueError("Alias lexicon is smaller than the node universe")
    if len(set(lexicon)) != len(lexicon):
        raise ValueError("Alias lexicon contains duplicates")
    rng = np.random.Generator(
        np.random.PCG64DXSM(seed64(master_seed, study_id, "semantic_aliases"))
    )
    shuffled = [str(lexicon[index]) for index in rng.permutation(len(lexicon))]
    return tuple(zip(sorted(map(str, canonical_nodes)), shuffled[: len(canonical_nodes)]))


def select_partial_edges(
    directed_edges: Sequence[Sequence[str]], master_seed: int, study_id: str
) -> tuple[tuple[str, str], ...]:
    edges = tuple(sorted((str(source), str(target)) for source, target in directed_edges))
    count = (len(edges) + 1) // 2
    ranked = sorted(
        edges,
        key=lambda edge: stable_rank(
            seed64(master_seed, study_id, "semantic_partial_edges"), *edge
        ),
    )
    return tuple(sorted(ranked[:count]))


def ordered_edges(
    directed_edges: Sequence[Sequence[str]], master_seed: int, study_id: str
) -> tuple[tuple[str, str], ...]:
    edges = tuple(sorted((str(source), str(target)) for source, target in directed_edges))
    order_seed = seed64(master_seed, study_id, "semantic_clause_order")
    return tuple(
        sorted(edges, key=lambda edge: stable_rank(order_seed, *sorted(edge)))
    )


def public_builder_view(record: Mapping[str, Any]) -> dict[str, str]:
    """Return the exact allowlisted model input; metadata and alias map stay outside."""
    builder_input = record.get("builder_input")
    if not isinstance(builder_input, Mapping) or set(builder_input) != {"story"}:
        raise ValueError("Invalid public story builder_input")
    story = builder_input.get("story")
    if not isinstance(story, str):
        raise ValueError("Story must be text")
    return {"story": story}


def build_story_bundle(scm: Mapping[str, Any], config: Mapping[str, Any]) -> StoryBundle:
    study_id = str(scm["study_id"])
    scene_id = str(scm["scene_id"])
    dag = scm["oracle_dag"]
    nodes = tuple(map(str, dag["nodes"]))
    directed = tuple(sorted((str(a), str(b)) for a, b in dag["directed"]))
    aliases = assign_aliases(
        nodes, config["aliases"]["lexicon"], int(config["randomness"]["master_seed"]), study_id
    )
    alias_by_node = dict(aliases)
    partial = select_partial_edges(directed, int(config["randomness"]["master_seed"]), study_id)
    clause_order = ordered_edges(directed, int(config["randomness"]["master_seed"]), study_id)
    variable_text = ", ".join(sorted(alias_by_node.values()))
    intro = (
        f"This synthetic process contains the following measured quantities: {variable_text}. "
        "The statements below exhaustively describe which pairs have a direct connection. "
        "No unlisted pair has a direct connection."
    )
    directional_template = str(config["stories"]["directional_template"])
    symmetric_template = str(config["stories"]["symmetric_template"])
    public_records: list[dict[str, Any]] = []
    truth_variants: dict[str, Any] = {}
    for variant in VARIANTS:
        directional = set(directed if variant == "full" else partial if variant == "partial" else ())
        clauses: list[str] = []
        truth_clauses: list[dict[str, Any]] = []
        for source, target in clause_order:
            if (source, target) in directional:
                text = directional_template.format(
                    source=alias_by_node[source], target=alias_by_node[target]
                )
                kind = "directional"
            else:
                left, right = sorted((alias_by_node[source], alias_by_node[target]))
                text = symmetric_template.format(left=left, right=right)
                kind = "symmetric"
            clauses.append(text)
            truth_clauses.append(
                {"source": source, "target": target, "kind": kind, "text": text}
            )
        story = " ".join((intro, *clauses))
        public_records.append(
            {
                "schema_version": "fourgraph.p1_public_story.v1",
                "artifact_id": f"{study_id}:{variant}",
                "study_id": study_id,
                "scene_id": scene_id,
                "evidence_variant": variant,
                "builder_input": {"story": story},
            }
        )
        truth_variants[variant] = {
            "directional_edges": [list(edge) for edge in sorted(directional)],
            "symmetric_edges": [list(edge) for edge in sorted(set(directed) - directional)],
            "clauses": truth_clauses,
        }
    truth = {
        "schema_version": "fourgraph.p1_story_truth.v1",
        "study_id": study_id,
        "scene_id": scene_id,
        "oracle_edges": [list(edge) for edge in directed],
        "partial_directional_edges": [list(edge) for edge in partial],
        "variants": truth_variants,
    }
    return StoryBundle(
        study_id=study_id,
        scene_id=scene_id,
        alias_map=aliases,
        clause_order=clause_order,
        partial_directional_edges=partial,
        public_records=tuple(public_records),
        truth_record=truth,
    )


def validate_story_bundle(bundle: StoryBundle, config: Mapping[str, Any]) -> dict[str, int]:
    alias_by_node = dict(bundle.alias_map)
    node_by_alias = {alias: node for node, alias in bundle.alias_map}
    if len(alias_by_node) != len(bundle.alias_map) or len(set(alias_by_node.values())) != len(alias_by_node):
        raise RuntimeError(f"Alias uniqueness failure: {bundle.study_id}")
    oracle_edges = {tuple(edge) for edge in bundle.truth_record["oracle_edges"]}
    expected_partial = (len(oracle_edges) + 1) // 2
    if len(bundle.partial_directional_edges) != expected_partial:
        raise RuntimeError(f"Partial dose failure: {bundle.study_id}")
    counts: dict[str, int] = {}
    for record in bundle.public_records:
        variant = str(record["evidence_variant"])
        story = public_builder_view(record)["story"]
        if CANONICAL_ID.search(story) or "->" in story or "→" in story:
            raise RuntimeError(f"Forbidden machine identifier/arrow in {record['artifact_id']}")
        lowered = story.lower()
        if any(term in lowered for term in ("oracle", "dag", "cpdag", "edge weight", "seed=")):
            raise RuntimeError(f"Forbidden generator metadata in {record['artifact_id']}")
        truth = bundle.truth_record["variants"][variant]
        directional = {tuple(edge) for edge in truth["directional_edges"]}
        symmetric = {tuple(edge) for edge in truth["symmetric_edges"]}
        if directional | symmetric != oracle_edges or directional & symmetric:
            raise RuntimeError(f"Skeleton coverage failure: {record['artifact_id']}")
        if len(truth["clauses"]) != len(oracle_edges):
            raise RuntimeError(f"Clause cardinality failure: {record['artifact_id']}")
        parsed_directional: set[tuple[str, str]] = set()
        parsed_symmetric: set[frozenset[str]] = set()
        for clause in truth["clauses"]:
            text = str(clause["text"])
            if story.count(text) != 1:
                raise RuntimeError(f"Public clause occurrence failure: {record['artifact_id']}")
            directional_match = DIRECTIONAL_CLAUSE.fullmatch(text)
            symmetric_match = SYMMETRIC_CLAUSE.fullmatch(text)
            if directional_match:
                parsed = (
                    node_by_alias[directional_match.group("source")],
                    node_by_alias[directional_match.group("target")],
                )
                parsed_directional.add(parsed)
                if clause["kind"] != "directional" or parsed != (
                    clause["source"],
                    clause["target"],
                ):
                    raise RuntimeError(f"Directional text/truth mismatch: {record['artifact_id']}")
            elif symmetric_match:
                parsed_pair = frozenset(
                    (
                        node_by_alias[symmetric_match.group("left")],
                        node_by_alias[symmetric_match.group("right")],
                    )
                )
                parsed_symmetric.add(parsed_pair)
                if clause["kind"] != "symmetric" or parsed_pair != frozenset(
                    (clause["source"], clause["target"])
                ):
                    raise RuntimeError(f"Symmetric text/truth mismatch: {record['artifact_id']}")
            else:
                raise RuntimeError(f"Unparseable public clause: {record['artifact_id']}")
        if parsed_directional != directional:
            raise RuntimeError(f"Parsed directional-claim mismatch: {record['artifact_id']}")
        expected_symmetric = {frozenset(edge) for edge in symmetric}
        if parsed_symmetric != expected_symmetric:
            raise RuntimeError(f"Parsed symmetric-claim mismatch: {record['artifact_id']}")
        expected = len(oracle_edges) if variant == "full" else expected_partial if variant == "partial" else 0
        if len(directional) != expected:
            raise RuntimeError(f"Directional dose failure: {record['artifact_id']}")
        counts[variant] = len(directional)
    return counts


def evidence_class(variant: str) -> str:
    return {"full": "all_directional", "partial": "mixed", "ambiguous": "none_directional"}[variant]


def blinded_slot_order(master_seed: int, study_id: str) -> tuple[str, ...]:
    """Return a reproducible, scene-specific permutation of the hidden variant labels."""
    stream_seed = seed64(master_seed, study_id, "blinded_variant_order")
    return tuple(
        sorted(
            VARIANTS,
            key=lambda variant: stable_rank(stream_seed, variant),
        )
    )
