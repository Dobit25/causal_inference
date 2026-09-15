import json
from pathlib import Path

import pytest

from fourgraph.p1_t21 import (
    h1_local_orientation,
    parse_preference_response,
    render_preference_prompt,
    select_threshold,
)
from fourgraph.partial_graph import PartialGraph


ROOT = Path(__file__).resolve().parents[1]


def test_preference_adapter_keeps_public_names_in_prompt_and_maps_after_response():
    parent = PartialGraph.build(["X000", "X001"], undirected=[("X000", "X001")])
    aliases = {"X000": "Beryl index", "X001": "Amber index"}
    prompt = render_preference_prompt(
        "Amber index influences Beryl index.", aliases, parent, "{{PAIRS_JSON}}\n{{STORY}}"
    )
    assert "X000" not in prompt and "X001" not in prompt
    raw = json.dumps(
        {
            "schema_version": "fourgraph.p1_semantic_preferences_response.v1",
            "preferences": [
                {
                    "left": "Amber index",
                    "right": "Beryl index",
                    "probability_left_causes_right": 0.9,
                    "evidence": "The story states this direction.",
                }
            ],
        }
    )
    artifact, _ = parse_preference_response(raw, aliases, parent)
    assert artifact["preferences"][0] == {
        "left": "X000",
        "right": "X001",
        "probability_left_causes_right": pytest.approx(0.1),
    }


def test_h1_fails_closed_when_local_preferences_leave_equivalence_class():
    parent = PartialGraph.build(
        ["X000", "X001", "X002"],
        undirected=[("X000", "X001"), ("X001", "X002"), ("X000", "X002")],
    )
    artifact = {
        "schema_version": "fourgraph.semantic_preferences.v1",
        "parent_graph_sha256": __import__("fourgraph.hybrid_h2", fromlist=["graph_sha256"]).graph_sha256(parent),
        "preferences": [
            {"left": "X000", "right": "X001", "probability_left_causes_right": 0.9},
            {"left": "X000", "right": "X002", "probability_left_causes_right": 0.1},
            {"left": "X001", "right": "X002", "probability_left_causes_right": 0.9},
        ],
    }
    with pytest.raises(ValueError):
        h1_local_orientation(parent, artifact)


def test_threshold_selection_uses_frozen_order():
    rows = [
        {"eligible": True, "orientation_coverage": 0.5, "confident_wrong_rate": 0.01, "tau_margin": 0.1, "tau_conflict": 0.1},
        {"eligible": True, "orientation_coverage": 0.5, "confident_wrong_rate": 0.01, "tau_margin": 0.05, "tau_conflict": 0.2},
    ]
    selected = select_threshold(rows)
    assert (selected["tau_margin"], selected["tau_conflict"]) == (0.05, 0.2)


def test_t21_terminal_audit_and_development_boundary():
    audit = json.loads((ROOT / "data/manifests/t21_development_audit.json").read_text(encoding="utf-8"))
    assert audit["counts"]["development_scenes"] == 20
    assert audit["counts"]["semantic_preference_artifacts"] == 60
    assert audit["counts"]["api_attempts_captured"] == 80
    assert audit["counts"]["threshold_candidates"] == 20
    assert audit["selected_threshold"] is None
    assert audit["verdict"]["protocol_amendment_required"] is True
    assert audit["verdict"]["t22_holdout_freeze_authorized"] is False
    assert audit["evidence_boundary"]["holdout_accessed"] is False


def test_t21_manifests_contain_development_only_and_expected_counts():
    split = json.loads((ROOT / "data/manifests/t18_p1_frozen_split.json").read_text(encoding="utf-8"))
    dev = set(split["development_ids"])
    holdout = set(split["holdout_ids"])
    graphs = [json.loads(line) for line in (ROOT / "data/manifests/t21_dev_graphs.jsonl").read_text(encoding="utf-8").splitlines()]
    metrics = [json.loads(line) for line in (ROOT / "data/manifests/t21_dev_structural_metrics.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(graphs) == 160
    assert len(metrics) == 180
    assert {row["study_id"] for row in graphs} == dev
    assert not ({row["study_id"] for row in graphs} & holdout)
    assert all("H2_SELECTIVE" not in row["condition"] for row in graphs)
