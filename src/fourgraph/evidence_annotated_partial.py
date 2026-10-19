"""Validation contract for a statistical CPDAG plus certified-direction overlay."""
from __future__ import annotations

from dataclasses import dataclass

from .partial_graph import PartialGraph, consistent_extension, unshielded_colliders, validate_cpdag


@dataclass(frozen=True)
class OverlayValidation:
    valid: bool
    reason: str | None


def validate_evidence_annotated_overlay(
    parent: PartialGraph,
    semantic_selected: set[tuple[str, str]],
) -> OverlayValidation:
    """Validate a semantic overlay without mutating/demoting the parent CPDAG.

    `semantic_selected` may orient only parent-undirected adjacencies.  The
    resulting constraints must retain a DAG extension of the original parent
    CPDAG; parent compelled arrows remain constraints even if their display
    overlay is intentionally withheld.
    """
    try:
        validate_cpdag(parent)
    except ValueError as exc:
        return OverlayValidation(False, f"invalid parent CPDAG: {exc}")
    selected_skeleton = {tuple(sorted(edge)) for edge in semantic_selected}
    if len(selected_skeleton) != len(semantic_selected):
        return OverlayValidation(False, "duplicate or antiparallel semantic direction")
    if not selected_skeleton.issubset(parent.undirected):
        return OverlayValidation(False, "semantic direction is not on a parent-undirected edge")
    try:
        constrained = PartialGraph.build(
            parent.nodes,
            set(parent.directed) | set(semantic_selected),
            set(parent.undirected) - selected_skeleton,
        )
        extension = consistent_extension(constrained)
    except ValueError as exc:
        return OverlayValidation(False, str(exc))
    if not parent.directed.issubset(extension.directed):
        return OverlayValidation(False, "extension violates a parent compelled direction")
    if unshielded_colliders(extension) != unshielded_colliders(parent):
        return OverlayValidation(False, "semantic overlay changes parent collider constraints")
    return OverlayValidation(True, None)
