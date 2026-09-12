from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import yaml

from fourgraph.conformance_audit import independent_answer_class, independent_target
from fourgraph.reasoner import TASKS


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "data/manifests/t12_v3_synthetic_conformance.jsonl"
AUDIT = ROOT / "data/manifests/t12_v3_synthetic_conformance_audit.json"
PANEL = ROOT / "data/manifests/t12_v3_manual_review_panel.jsonl"
SMOKE = ROOT / "data/manifests/t12_v3_openai_mini_smoke.json"
CANDIDATE = ROOT / "configs/t12_v3_openai_mini.yaml"
FULL_CANDIDATE = ROOT / "configs/t12_v3_openai_mini_full.yaml"
SMOKE_AUDIT = ROOT / "data/manifests/t12_v3_openai_mini_smoke_audit.json"
FULL_SCORES = ROOT / "data/manifests/t12_v3_openai_mini_conformance_scores.jsonl"
FULL_AUDIT = ROOT / "data/manifests/t12_v3_openai_mini_conformance_audit.json"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_v3_suite_has_exact_registered_balance_and_no_benchmark_evidence() -> None:
    rows = _rows(SUITE)
    assert len(rows) == 150
    assert Counter(row["task_id"] for row in rows) == Counter({task: 30 for task in TASKS})
    assert Counter(row["bucket"] for row in rows) == {
        "dag_answered": 90,
        "cpdag_answered": 30,
        "cpdag_undetermined": 30,
    }
    assert Counter(row["answer_class"] for row in rows) == {
        "valid_nonempty_set": 40,
        "valid_empty_set": 40,
        "no_valid_adjustment_set": 40,
        "undetermined": 30,
    }
    assert all(len(row["graph"]["nodes"]) == 5 for row in rows)
    assert all(not row["uses_causalds_story"] for row in rows)
    assert all(not row["uses_causalds_answer"] for row in rows)
    forbidden_keys = {"story", "public_story", "gold_answer", "answer", "scene_id"}
    assert all(not (forbidden_keys & set(row)) for row in rows)


def test_v3_independent_solver_matches_all_150_targets_and_classes() -> None:
    for row in _rows(SUITE):
        assert independent_target(row) == row["expected"]
        assert independent_answer_class(row) == row["answer_class"]
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["production_target_matches"] == 150
    assert audit["independent_answer_class_matches"] == 150
    assert audit["v2_case_identity_overlap"] == 0
    assert audit["feature_minimums_met"] is True
    assert audit["measurement_ready_for_model_screening"] is True


def test_v3_manual_panel_and_smoke_are_stratified_and_frozen() -> None:
    rows = _rows(SUITE)
    by_id = {row["case_id"]: row for row in rows}
    panel = _rows(PANEL)
    assert len(panel) == 20
    assert Counter(row["task_id"] for row in panel) == Counter({task: 4 for task in TASKS})
    assert set(row["stratum"] for row in panel) == {
        "dag_valid_nonempty",
        "dag_no_valid_direct_reverse",
        "cpdag_invariant_valid_empty",
        "cpdag_undetermined",
    }
    assert all(row["independent_target"] == row["expected"] for row in panel)
    assert all(all(row["review_checklist"].values()) for row in panel)

    smoke = json.loads(SMOKE.read_text(encoding="utf-8"))
    selected = [by_id[case_id] for case_id in smoke["case_ids"]]
    assert len(selected) == len(set(smoke["case_ids"])) == 10
    assert Counter(row["task_id"] for row in selected) == Counter({task: 2 for task in TASKS})
    assert set(row["answer_class"] for row in selected) == {
        "valid_nonempty_set",
        "valid_empty_set",
        "no_valid_adjustment_set",
        "undetermined",
    }
    assert {row["bucket"] for row in selected} == {
        "dag_answered",
        "cpdag_answered",
        "cpdag_undetermined",
    }


def test_v3_live_candidate_pins_every_scientific_input() -> None:
    config = yaml.safe_load(CANDIDATE.read_text(encoding="utf-8"))
    frozen = config["frozen_inputs"]
    assert config["reasoner"]["reasoning_effort"] == "medium"
    assert config["reasoner"]["max_output_tokens"] == 10240
    assert config["live_execution"] == {
        "allowed": True,
        "next_action": "ten_case_smoke_only",
        "conformance_auto_start_allowed": False,
    }
    assert config["holdout"]["accessed"] is False
    for path_key, hash_key in (
        ("prompt_contract", "prompt_contract_sha256"),
        ("suite", "suite_sha256"),
        ("measurement_audit", "measurement_audit_sha256"),
        ("manual_review_panel", "manual_review_panel_sha256"),
        ("smoke_manifest", "smoke_manifest_sha256"),
    ):
        assert _sha(ROOT / frozen[path_key]) == frozen[hash_key]
    for item in frozen["response_schemas"].values():
        assert _sha(ROOT / item["path"]) == item["sha256"]


def test_v3_generator_reproduces_all_four_artifacts_byte_for_byte() -> None:
    path = ROOT / "scripts/build_t12_v3_conformance.py"
    spec = importlib.util.spec_from_file_location("build_t12_v3_conformance", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    generated = module.build()
    assert generated == tuple(path.read_bytes() for path in (SUITE, AUDIT, PANEL, SMOKE))


def test_v3_live_smoke_passed_engineering_only_and_kept_holdout_closed() -> None:
    audit = json.loads(SMOKE_AUDIT.read_text(encoding="utf-8"))
    assert audit["schema_version"] == "fourgraph.t12_v3_openai_smoke_audit.v1"
    assert audit["cases"] == audit["captured_calls"] == 10
    assert audit["retry_calls"] == 0
    assert audit["strict_accuracy_diagnostic_only"] == 0.9
    assert audit["smoke_technical_passed"] is True
    assert all(audit["technical_gate_results"].values())
    assert audit["scientific_gate_applied"] is False
    assert audit["holdout_accessed"] is False
    assert audit["config_sha256"] == _sha(CANDIDATE)


def test_v3_full_candidate_changes_only_lifecycle_authorization() -> None:
    smoke = yaml.safe_load(CANDIDATE.read_text(encoding="utf-8"))
    full = yaml.safe_load(FULL_CANDIDATE.read_text(encoding="utf-8"))
    assert full["parent_candidate"]["config_sha256"] == _sha(CANDIDATE)
    assert full["parent_candidate"]["smoke_audit_sha256"] == _sha(SMOKE_AUDIT)
    for field in ("reasoner", "evidence_contract", "frozen_inputs"):
        assert full[field] == smoke[field]
    assert full["calibration"]["prospective_gates"] == smoke["calibration"]["prospective_gates"]
    assert full["live_execution"]["next_action"] == "full_150_conformance"
    assert full["live_execution"]["conformance_auto_start_allowed"] is True
    assert full["live_execution"]["oracle_development_auto_start_allowed"] is False
    assert full["holdout"]["accessed"] is False


def test_v3_full_conformance_passes_registered_gates_and_stops_before_oracle() -> None:
    records = _rows(FULL_SCORES)
    audit = json.loads(FULL_AUDIT.read_text(encoding="utf-8"))
    assert len(records) == 150
    assert sum(row["strict_correct"] for row in records) == 146
    assert Counter(row["task_id"] for row in records) == Counter({task: 30 for task in TASKS})
    assert audit["schema_version"] == "fourgraph.t12_v3_openai_conformance_audit.v1"
    assert audit["parse_success_rate"] == 1.0
    assert audit["first_attempt_schema_compliance_rate"] == 0.96666667
    assert audit["strict_overall_accuracy"] == 0.97333333
    assert audit["strict_accuracy"]["bucket:dag_answered"] == 0.96666667
    assert audit["strict_accuracy"]["bucket:cpdag_answered"] == 0.96666667
    assert audit["strict_accuracy"]["bucket:cpdag_undetermined"] == 1.0
    assert all(audit["gate_results"].values())
    assert audit["all_gates_passed"] is True
    assert audit["causalds_oracle_development_eligible"] is True
    assert audit["engineering_diagnostics"]["incomplete_calls"] == 5
    assert audit["engineering_diagnostics"]["headroom_gate_passed"] is False
    assert audit["holdout_accessed"] is False
    assert audit["config_sha256"] == _sha(FULL_CANDIDATE)
    assert audit["records_sha256"] == _sha(FULL_SCORES)
