from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from fourgraph.conformance_audit import independent_target, semantic_equivalent
from fourgraph.llm_backend import LLMCallRequest
from fourgraph.t12_openai_backend import T12OpenAIResponsesBackend


ROOT = Path(__file__).resolve().parents[1]


def _suite() -> list[dict]:
    return [
        json.loads(line)
        for line in (ROOT / "data/manifests/t12_v2_synthetic_conformance.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]


def test_measurement_audit_is_independent_and_complete() -> None:
    rows = _suite()
    assert len(rows) == 150
    assert all(independent_target(row) == row["expected"] for row in rows)
    audit = json.loads(
        (ROOT / "data/manifests/t12_v2_measurement_audit.json").read_text(
            encoding="utf-8"
        )
    )
    panel = [
        json.loads(line)
        for line in (ROOT / "data/manifests/t12_v2_manual_review_panel.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    assert audit["production_target_matches"] == 150
    assert audit["production_target_mismatches"] == 0
    assert audit["measurement_ready_for_model_screening"] is True
    assert audit["holdout_accessed"] is False
    assert len(panel) == 20
    assert {sum(item["task_id"] == task for item in panel) for task in {
        row["task_id"] for row in rows
    }} == {4}
    assert {item["stratum"] for item in panel} == {
        "dag_non_no_backdoor",
        "dag_no_backdoor",
        "cpdag_invariant",
        "cpdag_undetermined",
    }


def test_semantic_equivalence_is_diagnostic_not_a_strict_replacement() -> None:
    no_backdoor_count = {"status": "answered", "accepted": ["no_backdoor"]}
    assert semantic_equivalent(
        task_id="identification__n_valid_adjustment_sets",
        parsed_status="answered",
        parsed_answer=0,
        expected=no_backdoor_count,
    )
    assert semantic_equivalent(
        task_id="identification__all_minimal_adjustment_sets",
        parsed_status="answered",
        parsed_answer=(),
        expected=no_backdoor_count,
    )
    assert not semantic_equivalent(
        task_id="identification__minimal_adjustment_set_size",
        parsed_status="answered",
        parsed_answer=0,
        expected=no_backdoor_count,
    )


def test_openai_candidate_freezes_gemma_inputs_and_smoke_is_balanced() -> None:
    config = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini.yaml").read_text(encoding="utf-8")
    )
    gemma = yaml.safe_load(
        (ROOT / "configs/t12_v2_design.yaml").read_text(encoding="utf-8")
    )
    assert config["reasoner"] == {
        "provider": "openai",
        "model_id": "gpt-5.4-mini-2026-03-17",
        "model_version": "gpt-5.4-mini-2026-03-17",
        "endpoint": "/v1/responses",
        "sdk": "openai",
        "sdk_version": "3.6.0",
        "credential_env": "OPENAI_API_KEY",
        "reasoning_effort": "high",
        "sampling_temperature": "omitted",
        "max_output_tokens": 4096,
        "max_validation_retries": 2,
        "transport_max_retries": 2,
        "timeout_seconds": 180,
        "service_tier": "default",
        "store": False,
        "structured_outputs": True,
        "provider_schema_transform": "openai_strict_subset_then_full_local_validation",
    }
    assert config["frozen_inputs"]["prompt"] == gemma["reasoner"]["prompt"]
    assert config["frozen_inputs"]["suite"] == gemma["calibration"]["suite"]
    assert config["holdout"]["accessed"] is False
    assert config["holdout"]["eligible"] is False

    rows = {row["case_id"]: row for row in _suite()}
    smoke = json.loads(
        (ROOT / "data/manifests/t12_v2_openai_mini_smoke.json").read_text(
            encoding="utf-8"
        )
    )
    selected = [rows[case_id] for case_id in smoke["case_ids"]]
    assert len(selected) == 10
    assert {sum(row["task_id"] == task for row in selected) for task in {
        row["task_id"] for row in selected
    }} == {2}
    assert {row["bucket"] for row in selected} >= {
        "dag_answered",
        "cpdag_undetermined",
    }
    tags = {tag for row in selected for tag in row["feature_tags"]}
    assert "empty_adjustment_set" in tags
    assert any(row["expected"]["accepted"] == ["no_backdoor"] for row in selected)


def test_openai_mini_b_changes_only_output_budget_in_scientific_runtime() -> None:
    original = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini.yaml").read_text(encoding="utf-8")
    )
    candidate = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini_b.yaml").read_text(encoding="utf-8")
    )
    assert candidate["single_planned_change"] == {
        "field": "reasoner.max_output_tokens",
        "from": 4096,
        "to": 8192,
    }
    left = dict(original["reasoner"])
    right = dict(candidate["reasoner"])
    assert left.pop("max_output_tokens") == 4096
    assert right.pop("max_output_tokens") == 8192
    assert left == right
    for field in (
        "evidence_contract",
        "frozen_inputs",
        "measurement_audit",
        "smoke",
        "calibration",
        "oracle_development_gate",
    ):
        assert candidate[field] == original[field]
    assert candidate["outputs"] != original["outputs"]
    assert candidate["holdout"]["accessed"] is False
    assert candidate["holdout"]["eligible"] is False


def test_openai_mini_c_changes_only_output_budget_and_adds_headroom_gate() -> None:
    parent = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini_b.yaml").read_text(encoding="utf-8")
    )
    candidate = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini_c.yaml").read_text(encoding="utf-8")
    )
    assert candidate["single_planned_change"] == {
        "field": "reasoner.max_output_tokens",
        "from": 8192,
        "to": 10240,
    }
    left = dict(parent["reasoner"])
    right = dict(candidate["reasoner"])
    assert left.pop("max_output_tokens") == 8192
    assert right.pop("max_output_tokens") == 10240
    assert left == right
    for field in (
        "evidence_contract",
        "frozen_inputs",
        "measurement_audit",
        "calibration",
        "oracle_development_gate",
    ):
        assert candidate[field] == parent[field]
    parent_smoke = dict(parent["smoke"])
    candidate_smoke = dict(candidate["smoke"])
    parent_gate = dict(parent_smoke.pop("technical_gate"))
    candidate_gate = dict(candidate_smoke.pop("technical_gate"))
    assert parent_smoke == candidate_smoke
    assert candidate_gate.pop("max_output_token_utilization_max") == 0.80
    assert candidate_gate == parent_gate
    assert candidate["holdout"]["accessed"] is False
    assert candidate["holdout"]["eligible"] is False


def test_openai_mini_d_changes_only_reasoning_effort() -> None:
    parent = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini_c.yaml").read_text(encoding="utf-8")
    )
    candidate = yaml.safe_load(
        (ROOT / "configs/t12_v2_openai_mini_d.yaml").read_text(encoding="utf-8")
    )
    assert candidate["single_planned_change"] == {
        "field": "reasoner.reasoning_effort",
        "from": "high",
        "to": "medium",
    }
    left = dict(parent["reasoner"])
    right = dict(candidate["reasoner"])
    assert left.pop("reasoning_effort") == "high"
    assert right.pop("reasoning_effort") == "medium"
    assert left == right
    for field in (
        "evidence_contract",
        "frozen_inputs",
        "measurement_audit",
        "smoke",
        "calibration",
        "oracle_development_gate",
        "budget",
    ):
        assert candidate[field] == parent[field]
    assert candidate["outputs"] != parent["outputs"]
    assert candidate["holdout"]["accessed"] is False
    assert candidate["holdout"]["eligible"] is False


class _FakeResponse:
    status = "completed"
    incomplete_details = None
    output_text = '{"k":0}'
    model = "gpt-5.4-mini-2026-03-17"
    _request_id = "req_test"
    system_fingerprint = "fp_test"
    service_tier = "default"
    usage = SimpleNamespace(
        input_tokens=123,
        output_tokens=45,
        input_tokens_details=SimpleNamespace(cached_tokens=100),
        output_tokens_details=SimpleNamespace(reasoning_tokens=40),
    )

    def model_dump(self, *, mode: str) -> dict:
        assert mode == "json"
        return {"id": self._request_id, "model": self.model, "status": self.status}


def test_openai_transport_omits_temperature_and_records_reasoning_usage() -> None:
    captured: dict = {}

    class _Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    backend = T12OpenAIResponsesBackend.__new__(T12OpenAIResponsesBackend)
    backend._client = SimpleNamespace(responses=_Responses())
    backend._response_schema = {
        "type": "object",
        "properties": {"k": {"type": "integer"}},
        "required": ["k"],
        "additionalProperties": False,
    }
    backend._response_schema_name = "test_schema"
    backend._model_version = "gpt-5.4-mini-2026-03-17"
    backend._reasoning_effort = "high"
    backend._service_tier = "default"
    backend._store = False
    backend._sdk_version = "3.6.0"
    result = backend.complete(
        LLMCallRequest(
            scene_id="SYN001",
            attempt=0,
            prompt="frozen prompt",
            provider="openai",
            model_id="gpt-5.4-mini-2026-03-17",
            model_version="gpt-5.4-mini-2026-03-17",
            temperature=0,
            max_tokens=4096,
            seed=None,
        )
    )
    assert "temperature" not in captured
    assert captured["reasoning"] == {"effort": "high"}
    assert captured["service_tier"] == "default"
    assert captured["store"] is False
    assert result.request_id == "req_test"
    assert result.reasoning_tokens == 40
    assert result.cached_input_tokens == 100
    assert result.output_tokens == 45
    assert result.response_status == "completed"
    assert result.incomplete_reason is None


def test_openai_transport_rejects_snapshot_drift() -> None:
    class _DriftResponse(_FakeResponse):
        model = "gpt-5.4-mini"

    backend = T12OpenAIResponsesBackend.__new__(T12OpenAIResponsesBackend)
    backend._client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: _DriftResponse())
    )
    backend._response_schema = {"type": "object"}
    backend._response_schema_name = "test_schema"
    backend._model_version = "gpt-5.4-mini-2026-03-17"
    backend._reasoning_effort = "high"
    backend._service_tier = "default"
    backend._store = False
    backend._sdk_version = "3.6.0"
    with pytest.raises(RuntimeError, match="snapshot drift"):
        backend.complete(
            LLMCallRequest(
                scene_id="SYN001",
                attempt=0,
                prompt="frozen prompt",
                provider="openai",
                model_id="gpt-5.4-mini-2026-03-17",
                model_version="gpt-5.4-mini-2026-03-17",
                temperature=0,
                max_tokens=4096,
                seed=None,
            )
        )


def test_failed_smoke_stops_before_conformance_and_holdout() -> None:
    audit = json.loads(
        (ROOT / "data/manifests/t12_v2_openai_mini_smoke_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["smoke_technical_passed"] is False
    assert audit["valid_cases_before_stop"] == 1
    assert audit["failed_case_id"] == "SYN024"
    assert audit["failed_case_attempts"] == 3
    assert {
        (item["response_status"], item["incomplete_reason"])
        for item in audit["failed_attempt_statuses"]
    } == {("incomplete", "max_output_tokens")}
    assert all(
        item["reasoning_tokens"] == 4096
        and item["visible_output_characters"] == 0
        for item in audit["failed_attempt_statuses"]
    )
    assert audit["conformance_150_started"] is False
    assert audit["causalds_oracle_development_eligible"] is False
    assert audit["full_development_matrix_eligible"] is False
    assert audit["holdout_accessed"] is False


def test_mini_b_smoke_passes_technical_gate_without_opening_next_stage() -> None:
    audit = json.loads(
        (ROOT / "data/manifests/t12_v2_openai_mini_b_smoke_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["max_output_tokens"] == 8192
    assert audit["cases"] == 10
    assert audit["captured_calls"] == 10
    assert audit["retry_calls"] == 0
    assert audit["smoke_technical_passed"] is True
    assert all(audit["technical_gate_results"].values())
    assert audit["strict_accuracy_diagnostic_only"] == 0.9
    assert audit["reasoning_tokens_distribution"] == {
        "min": 447,
        "median": 2396.0,
        "max": 7937,
    }
    assert audit["scientific_gate_applied"] is False
    assert audit["holdout_accessed"] is False


def test_mini_c_smoke_exposes_retry_hidden_token_ceiling() -> None:
    audit = json.loads(
        (ROOT / "data/manifests/t12_v2_openai_mini_c_smoke_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["max_output_tokens"] == 10240
    assert audit["cases"] == 10
    assert audit["captured_calls"] == 11
    assert audit["retry_calls"] == 1
    assert audit["max_output_token_utilization"] == 1.0
    assert audit["max_output_token_utilization_gate"] == 0.8
    assert audit["technical_gate_results"]["parsed"] is True
    assert audit["technical_gate_results"]["max_output_token_utilization"] is False
    assert audit["smoke_technical_passed"] is False
    assert audit["strict_accuracy_diagnostic_only"] == 0.8
    assert audit["scientific_gate_applied"] is False
    assert audit["holdout_accessed"] is False


def test_mini_d_medium_smoke_passes_headroom_without_opening_next_stage() -> None:
    audit = json.loads(
        (ROOT / "data/manifests/t12_v2_openai_mini_d_smoke_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert audit["reasoning_effort"] == "medium"
    assert audit["max_output_tokens"] == 10240
    assert audit["cases"] == 10
    assert audit["captured_calls"] == 10
    assert audit["retry_calls"] == 0
    assert audit["max_output_token_utilization"] == 0.36259766
    assert audit["max_output_token_utilization_gate"] == 0.8
    assert all(audit["technical_gate_results"].values())
    assert audit["smoke_technical_passed"] is True
    assert audit["strict_accuracy_diagnostic_only"] == 0.7
    assert audit["reasoning_tokens_distribution"] == {
        "min": 286,
        "median": 1248.5,
        "max": 3689,
    }
    assert audit["scientific_gate_applied"] is False
    assert audit["holdout_accessed"] is False


def test_mini_d_conformance_is_complete_but_fails_scientific_gates() -> None:
    audit = json.loads(
        (ROOT / "data/manifests/t12_v2_openai_mini_d_conformance_audit.json").read_text(
            encoding="utf-8"
        )
    )
    records = [
        json.loads(line)
        for line in (
            ROOT / "data/manifests/t12_v2_openai_mini_d_conformance_scores.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(records) == 150
    assert audit["reasoning_effort"] == "medium"
    assert audit["max_output_tokens"] == 10240
    assert audit["parse_success_rate"] == 1.0
    assert audit["first_attempt_schema_compliance_rate"] == 1.0
    assert audit["strict_overall_accuracy"] == 0.7
    assert audit["strict_accuracy"] == {
        "bucket:cpdag_answered": 0.925,
        "bucket:cpdag_undetermined": 0.74285714,
        "bucket:dag_answered": 0.56,
        "task:bias_diagnostic__forbidden_controls_list": 0.23333333,
        "task:identification__all_minimal_adjustment_sets": 0.83333333,
        "task:identification__minimal_adjustment_set_size": 0.8,
        "task:identification__n_valid_adjustment_sets": 0.76666667,
        "task:identification__one_valid_adjustment_set": 0.86666667,
    }
    assert audit["engineering_diagnostics"] == {
        "captured_calls": 150,
        "retry_calls": 0,
        "completed_calls": 150,
        "incomplete_calls": 0,
        "max_output_token_utilization": 0.5046875,
        "max_output_token_utilization_gate": 0.8,
        "headroom_gate_passed": True,
        "reasoning_tokens_distribution": {
            "min": 117,
            "median": 369.0,
            "max": 5146,
        },
        "latency_ms_distribution": {
            "min": 1566,
            "median": 3627.0,
            "max": 31129,
        },
    }
    assert audit["gate_results"] == {
        "parse_success": True,
        "first_attempt_schema_compliance": True,
        "overall_accuracy": False,
        "dag_answered_accuracy": False,
        "cpdag_answered_accuracy": True,
        "cpdag_undetermined_accuracy": False,
        "per_task_accuracy": False,
    }
    assert audit["all_gates_passed"] is False
    assert audit["causalds_oracle_development_eligible"] is False
    assert audit["holdout_accessed"] is False
