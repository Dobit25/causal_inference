from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _jsonl(path: str):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]


def _hash(path: str):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_v3d_preflight_freeze_matches_executed_config_and_runner():
    freeze = _json("data/manifests/t21_v3d_preflight_freeze.json")
    assert freeze["config_sha256"] == _hash("configs/t21_v3d_validation.yaml")
    audit = _json("data/manifests/t21_v3d_validation_audit.json")
    assert freeze["runner_sha256"] == audit["live_execution_freeze"]["live_runner_sha256"]
    assert audit["live_execution_freeze"]["scientific_inputs_prompts_responses_scoring_changed"] is False
    assert freeze["frozen_execution"]["logical_semantic_calls"] == 60
    assert freeze["frozen_execution"]["threshold_candidates"] == 20
    assert freeze["verdict"]["automatic_final_holdout_continuation"] is False


def test_v3d_terminal_gate_failed_and_holdout_remains_sealed():
    audit = _json("data/manifests/t21_v3d_validation_audit.json")
    assert audit["counts"]["validation_scenes"] == 20
    assert audit["counts"]["boss_graphs"] == 20
    assert audit["counts"]["semantic_preference_artifacts"] == 60
    assert audit["counts"]["api_attempts_captured"] == 60
    assert audit["counts"]["validation_retry_responses"] == 0
    assert audit["counts"]["threshold_candidates"] == 20
    assert audit["selected_threshold"] is None
    assert audit["verdict"] == {
        "final_holdout_execution_authorized": False,
        "t21_v3d_complete": True,
        "t21_v3e_holdout_freeze_decision_authorized": True,
        "t22_final_holdout_freeze_authorized": False,
        "threshold_selected": False,
        "validation_gate_passed": False,
    }
    assert audit["evidence_boundary"]["final_holdout_accessed"] is False
    assert audit["evidence_boundary"]["validation_tasks_or_answers_accessed"] is False


def test_v3d_evaluated_exact_frozen_grid_without_posthoc_gate_change():
    rows = _jsonl("data/manifests/t21_v3d_validation_threshold_grid.jsonl")
    assert len(rows) == 20
    assert {(row["tau_semantic"], row["tau_global"]) for row in rows} == {
        (semantic, stability)
        for semantic in (0.80, 0.90, 0.95, 0.99, 0.999)
        for stability in (0.80, 0.90, 0.95, 1.00)
    }
    assert all(row["graph_validity"] == 1.0 for row in rows)
    assert all(row["eligible"] is False for row in rows)
    assert all(row["uses_downstream_tasks_or_answers"] is False for row in rows)
    assert all(row["uses_existing_development"] is False and row["uses_final_holdout"] is False for row in rows)
    best = max(rows, key=lambda row: (row["orientation_precision"], row["orientation_coverage"]))
    assert best["orientation_precision"] == 0.8556701031
    assert best["answered_edges"] == 97
    assert best["orientation_coverage"] == 0.455399061


def test_v3d_preferences_and_boss_outputs_are_validation_only():
    preferences = _jsonl("data/manifests/t21_v3d_validation_semantic_preferences.jsonl")
    boss = _jsonl("data/manifests/t21_v3d_validation_boss_graphs.jsonl")
    assert len(preferences) == 60 and len(boss) == 20
    assert {row["study_id"] for row in preferences} == {f"P1V{i:03d}" for i in range(20)}
    assert {row["study_id"] for row in boss} == {f"P1V{i:03d}" for i in range(20)}
    assert all(row["oracle_not_persisted"] is True for row in boss)
    assert (ROOT / "data/manifests/t21_v3d_validation_selected_graphs.jsonl").read_bytes() == b""


def test_v3d_runner_never_loads_validation_tasks_or_existing_p1_raw_tree():
    source = (ROOT / "scripts/run_t21_v3d_validation.py").read_text(encoding="utf-8").lower()
    assert "tasks_grading.json" not in source
    assert "data/generated/p1_hybrid_v1" not in source
    assert "t18_p1_frozen_split" not in source
