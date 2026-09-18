"""Small independent reference rules for semantic/veto conformance."""

from __future__ import annotations

from typing import Mapping, Sequence


def reference_agreement(labels: Sequence[str]) -> tuple[str, str | None]:
    if len(labels) != 6:
        raise ValueError("expected six labels")
    forward = sum(label == "A_TO_B" for label in labels)
    reverse = sum(label == "B_TO_A" for label in labels)
    unknown = sum(label == "UNDETERMINED" for label in labels)
    if forward + reverse + unknown != 6:
        raise ValueError("unknown label")
    if forward > 0 and reverse > 0:
        return "conflict", None
    direction = "A_TO_B" if forward else "B_TO_A" if reverse else None
    majority = forward if forward else reverse
    lookup = {(6, 0): "very_high", (5, 1): "high", (4, 2): "medium"}
    return lookup.get((majority, unknown), "uncertain"), direction


def reference_veto(
    statistical_status: str,
    agreement_class: str | None,
    semantic_direction: str | None,
    certified_safe: bool,
) -> tuple[str, str | None, str]:
    if statistical_status in ("weak_adjacency", "absent"):
        return "excluded", None, "statistical_veto"
    if statistical_status == "unavailable":
        return "unavailable", None, "method_failure"
    if statistical_status == "direction_uncertain":
        if agreement_class in ("very_high", "high") and certified_safe and semantic_direction:
            return "directed", semantic_direction, "semantic_selected"
        if agreement_class == "conflict":
            return "undirected", None, "conflict_abstained"
        return "undirected", None, "unresolved"
    statistical_direction = (
        "A_TO_B" if statistical_status == "statistical_direction_A_to_B" else "B_TO_A"
    )
    if agreement_class == "conflict":
        return "undirected", None, "conflict_abstained"
    if agreement_class in ("very_high", "high") and certified_safe and semantic_direction:
        if semantic_direction == statistical_direction:
            return "directed", statistical_direction, "statistical_semantic_agreement"
        return "undirected", None, "conflict_abstained"
    return "directed", statistical_direction, "statistical_stable"
