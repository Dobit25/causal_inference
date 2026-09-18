from __future__ import annotations

import copy

import pytest

from fourgraph.semantic_reliability import (
    PROMPT_IDS,
    RequestedPair,
    SemanticReliabilityContractError,
    aggregate_six_prompt_responses,
    apply_statistical_veto,
    build_empirical_reliability_records,
    classify_vote_counts,
    validate_whole_graph_response,
)


HASH = "A" * 64
PAIR = RequestedPair("pair-1", "Amber index", "Beryl index", "X000", "X001")
FORWARD = "Within this process, changes in Amber index directly influence Beryl index."
REVERSE = "Within this process, changes in Beryl index directly influence Amber index."
SYMMETRIC = (
    "Amber index and Beryl index are directly connected in the process, "
    "but this description does not establish which one influences the other."
)
STORY = " ".join((FORWARD, REVERSE, SYMMETRIC))


def response(label: str):
    if label == "A_TO_B":
        row = {"pair_id": "pair-1", "judgment": "directed", "cause": "Amber index", "effect": "Beryl index", "evidence_quote": FORWARD}
    elif label == "B_TO_A":
        row = {"pair_id": "pair-1", "judgment": "directed", "cause": "Beryl index", "effect": "Amber index", "evidence_quote": REVERSE}
    else:
        row = {"pair_id": "pair-1", "judgment": "undetermined", "cause": None, "effect": None, "evidence_quote": None}
    return {"schema_version": "fourgraph.semantic_whole_graph_response.v1", "judgments": [row]}


def semantic_record(labels: list[str]):
    responses = {prompt: response(label) for prompt, label in zip(PROMPT_IDS, labels)}
    return aggregate_six_prompt_responses(
        scene_id="SYN", story_variant="full", story=STORY,
        requested_pairs=[PAIR], responses=responses,
        prompt_bundle_sha256=HASH, story_sha256=HASH,
        requested_pairs_sha256=HASH, response_schema_sha256=HASH,
    )[0]


def reliability(agreement: str, status: str):
    return {
        "schema_version": "fourgraph.empirical_reliability.v1",
        "story_variant": "full", "agreement_class": agreement,
        "correct": 20, "total": 20, "independent_scenes": 20,
        "point_estimate": 1.0, "diagnostic_wilson_lower_95": 0.880866,
        "false_adjacencies_count_as_errors": True,
        "certification_status": status, "calibration_manifest_sha256": HASH,
    }


def statistical(status: str):
    return {"edge": ["X000", "X001"], "status": status}


def test_exact_quote_and_association_guard():
    assert validate_whole_graph_response(response("A_TO_B"), [PAIR], STORY) == {"pair-1": "A_TO_B"}
    bad = response("A_TO_B")
    bad["judgments"][0]["evidence_quote"] = SYMMETRIC
    with pytest.raises(SemanticReliabilityContractError, match="association-only"):
        validate_whole_graph_response(bad, [PAIR], STORY)


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ((6, 0, 0), ("very_high", "A_TO_B")),
        ((0, 5, 1), ("high", "B_TO_A")),
        ((4, 0, 2), ("medium", "A_TO_B")),
        ((3, 0, 3), ("uncertain", "A_TO_B")),
        ((1, 1, 4), ("conflict", None)),
        ((0, 0, 6), ("uncertain", None)),
    ],
)
def test_six_vote_classes(counts, expected):
    assert classify_vote_counts(*counts) == expected


def test_reliability_counts_false_adjacencies_as_errors_and_stays_pending():
    outcomes = [
        {"scene_id": "S1", "story_variant": "full", "agreement_class": "high", "published_direction": "A_TO_B", "oracle_relation": "A_TO_B"},
        {"scene_id": "S2", "story_variant": "full", "agreement_class": "high", "published_direction": "A_TO_B", "oracle_relation": "nonedge"},
    ]
    record = build_empirical_reliability_records(outcomes, calibration_manifest_sha256=HASH)[0]
    assert record["correct"] == 1 and record["total"] == 2
    assert record["point_estimate"] == 0.5
    assert record["certification_status"] == "pending_risk_control"


def test_statistical_veto_requires_certified_safe_semantics():
    semantic = semantic_record(["A_TO_B"] * 6)
    pending = apply_statistical_veto(
        statistical("direction_uncertain"), semantic, reliability("very_high", "pending_risk_control")
    )
    assert pending["decision"] == "undirected"
    safe = apply_statistical_veto(
        statistical("direction_uncertain"), semantic, reliability("very_high", "certified_safe")
    )
    assert (safe["decision"], safe["direction"], safe["source"]) == (
        "directed", "A_TO_B", "semantic_selected"
    )


def test_weak_edge_is_vetoed_and_safe_conflict_downgrades_stable_direction():
    semantic = semantic_record(["B_TO_A"] * 6)
    weak = apply_statistical_veto(
        statistical("weak_adjacency"), semantic, reliability("very_high", "certified_safe")
    )
    assert weak["decision"] == "excluded" and weak["statistical_veto_passed"] is False
    conflict = apply_statistical_veto(
        statistical("statistical_direction_A_to_B"), semantic, reliability("very_high", "certified_safe")
    )
    assert (conflict["decision"], conflict["source"]) == ("undirected", "conflict_abstained")


def test_response_duplicate_pair_and_corrupt_agreement_fail_closed():
    duplicated = response("A_TO_B")
    duplicated["judgments"].append(copy.deepcopy(duplicated["judgments"][0]))
    with pytest.raises(SemanticReliabilityContractError, match="exactly once"):
        validate_whole_graph_response(duplicated, [PAIR], STORY)
    semantic = semantic_record(["A_TO_B"] * 6)
    semantic["agreement_class"] = "medium"
    with pytest.raises(SemanticReliabilityContractError, match="does not match"):
        apply_statistical_veto(statistical("direction_uncertain"), semantic, None)
