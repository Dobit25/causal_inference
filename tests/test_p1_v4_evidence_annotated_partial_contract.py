from fourgraph.evidence_annotated_partial import validate_evidence_annotated_overlay
from fourgraph.partial_graph import PartialGraph


def test_unconfirmed_compelled_is_display_only_and_does_not_mutate_parent():
    parent = PartialGraph.build(("A", "B", "C"), {("A", "C"), ("B", "C")}, set())
    before = parent.to_dict()
    assert validate_evidence_annotated_overlay(parent, set()).valid
    assert parent.to_dict() == before


def test_semantic_orientation_must_be_on_parent_undirected_edge():
    parent = PartialGraph.build(("A", "B", "C"), {("A", "C")}, {("A", "B")})
    assert validate_evidence_annotated_overlay(parent, {("A", "C")}).valid is False


def test_compatible_semantic_overlay_preserves_parent_extension_constraints():
    parent = PartialGraph.build(("A", "B", "C"), set(), {("A", "B"), ("B", "C")})
    assert validate_evidence_annotated_overlay(parent, {("A", "B")}).valid


def test_incompatible_semantic_overlay_fails_closed_without_parent_repair():
    parent = PartialGraph.build(("A", "B", "C"), set(), {("A", "B"), ("B", "C"), ("A", "C")})
    result = validate_evidence_annotated_overlay(parent, {("A", "B"), ("B", "C"), ("C", "A")})
    assert result.valid is False
    assert parent.directed == set()
