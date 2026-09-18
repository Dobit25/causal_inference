from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def read_jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]


def test_semantic_conformance_is_balanced_and_passed() -> None:
    suite = read_jsonl("data/manifests/t21_v2_semantic_conformance.jsonl")
    audit = read_json("data/manifests/t21_v2_semantic_conformance_live_audit.json")
    assert len(suite) == 120
    assert Counter(row["expected_class"] for row in suite) == {
        "forward": 40,
        "reverse": 40,
        "ambiguous": 40,
    }
    assert audit["metrics"]["parse_success_rate"] == 1.0
    assert audit["metrics"]["first_attempt_schema_success_rate"] == 1.0
    assert audit["metrics"]["overall_accuracy"] == 1.0
    assert audit["verdict"]["full_conformance_passed"] is True
    assert audit["evidence_boundary"] == {
        "P1_accessed": False,
        "downstream_reasoner_executed": False,
        "holdout_accessed": False,
    }


def test_prompt_v2_explicitly_defines_all_three_directions() -> None:
    prompt = (ROOT / "prompts/p1_semantic_preferences_v2.md").read_text(encoding="utf-8")
    assert "`left` directly influences `right`" in prompt
    assert "`right` directly influences `left`" in prompt
    assert "0.5" in prompt
    assert "0.999" in prompt
    assert "0.001" in prompt


def test_development_gate_remains_failed_without_holdout() -> None:
    audit = read_json("data/manifests/t21_v2_development_audit.json")
    assert audit["counts"]["development_scenes"] == 20
    assert audit["counts"]["semantic_preference_artifacts"] == 60
    assert audit["counts"]["threshold_candidates"] == 20
    assert audit["selected_threshold"] is None
    assert audit["best_candidate_by_precision_then_coverage"]["orientation_precision"] == 0.7368421053
    assert audit["evidence_boundary"]["holdout_accessed"] is False
    assert audit["evidence_boundary"]["reasoner_executed"] is False
    assert audit["verdict"]["t22_holdout_freeze_authorized"] is False


def test_comparators_and_oracle_skeleton_diagnostic_are_non_primary() -> None:
    audit = read_json("data/manifests/t21_v2_comparator_audit.json")
    assert audit["counts"] == {
        "captured_api_attempts": 42,
        "comparator_graphs": 40,
        "comparator_logical_calls": 40,
        "development_scenes": 20,
        "diagnostic_records": 120,
        "validation_retry_attempts": 2,
    }
    assert audit["comparator_summary"]["partial"]["valid"] == 20
    assert audit["comparator_summary"]["ambiguous"]["valid"] == 20
    assert audit["evidence_boundary"]["comparators_used_for_threshold"] is False
    assert audit["evidence_boundary"]["holdout_accessed"] is False
    assert audit["verdict"]["t21_v2_passed"] is False
    assert audit["verdict"]["t22_authorized"] is False


def test_all_versioned_v2_scene_outputs_are_development_only() -> None:
    split = read_json("data/manifests/t18_p1_frozen_split.json")
    dev = set(split["development_ids"])
    holdout = set(split["holdout_ids"])
    paths = [
        "data/manifests/t21_v2_dev_semantic_preferences.jsonl",
        "data/manifests/t21_v2_dev_graphs.jsonl",
        "data/manifests/t21_v2_dev_llm_comparator_graphs.jsonl",
        "data/manifests/t21_v2_oracle_skeleton_diagnostic.jsonl",
    ]
    for path in paths:
        ids = {row["study_id"] for row in read_jsonl(path)}
        assert ids <= dev
        assert ids.isdisjoint(holdout)


def test_oracle_skeleton_diagnostic_reports_both_parents_without_selecting() -> None:
    rows = read_jsonl("data/manifests/t21_v2_oracle_skeleton_diagnostic.jsonl")
    assert len(rows) == 120
    assert Counter((row["story_variant"], row["parent"]) for row in rows) == {
        (variant, parent): 20
        for variant in ("full", "partial", "ambiguous")
        for parent in ("boss_cpdag", "oracle_cpdag")
    }
    assert all(row["uses_threshold_selection"] is False for row in rows)
    assert all(row["uses_holdout"] is False for row in rows)
