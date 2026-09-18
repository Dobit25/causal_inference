from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_v3e_records_terminal_failed_gate_without_threshold():
    audit = _json("data/manifests/t21_v3e_terminal_audit.json")
    assert audit["decision"] == "STOP_P1_V2_BEFORE_FINAL_HOLDOUT"
    assert audit["terminal_result"]["best_orientation_correct"] == 83
    assert audit["terminal_result"]["best_answered_edges"] == 97
    assert audit["terminal_result"]["best_orientation_precision"] == 0.8556701031
    assert audit["terminal_result"]["required_orientation_precision"] == 0.95
    assert audit["terminal_result"]["selected_threshold"] is None


def test_v3e_keeps_final_holdout_and_t22_sealed():
    audit = _json("data/manifests/t21_v3e_terminal_audit.json")
    assert audit["evidence_boundary"]["api_calls"] == 0
    assert audit["evidence_boundary"]["final_holdout_accessed"] is False
    assert audit["evidence_boundary"]["final_holdout_method_results_created"] is False
    assert audit["verdict"]["t22_authorized"] is False
    assert audit["verdict"]["final_holdout_execution_authorized"] is False
    assert (ROOT / "data/manifests/t21_v3d_validation_selected_graphs.jsonl").read_bytes() == b""


def test_v3e_hash_pins_every_listed_v2_v3_artifact():
    audit = _json("data/manifests/t21_v3e_terminal_audit.json")
    artifacts = audit["freeze"]["artifacts"]
    assert audit["freeze"]["artifact_count"] == len(artifacts)
    assert len(artifacts) >= 60
    assert len({row["path"] for row in artifacts}) == len(artifacts)
    for row in artifacts:
        assert row["sha256"] == _hash(row["path"])
        assert row["bytes"] == (ROOT / row["path"]).stat().st_size


def test_v3e_authorizes_design_only_successor_with_user_frozen_choices():
    audit = _json("data/manifests/t21_v3e_terminal_audit.json")
    successor = audit["successor_boundary"]
    assert successor["authorized_action"] == "P1_V3_EVIDENCE_SELECTIVE_PROTOCOL_DESIGN_ONLY"
    assert successor["bootstrap_boss_execution_authorized"] is False
    assert successor["semantic_api_calls_authorized"] is False
    assert successor["final_holdout_access_authorized"] is False
    assert successor["frozen_user_decisions"] == {
        "primary_statistical_method": "bootstrap_boss",
        "scd_ensemble_role": "deferred_robustness_extension",
        "semantic_call_granularity": "whole_graph",
        "semantic_model": "gpt-5.4-nano-2026-03-17",
    }
