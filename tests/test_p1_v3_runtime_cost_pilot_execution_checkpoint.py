from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fourgraph.runtime_cost_pilot_live import PilotBudgetController


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_official_nano_rate_and_snapshot_are_pinned():
    rate = _json("configs/p1_v3_runtime_cost_pilot_official_rate_card.json")
    assert rate["snapshot"] == "gpt-5.4-nano-2026-03-17"
    assert rate["processing_tier"] == "standard"
    assert rate["short_context"] == {
        "input": 0.20, "cached_input": 0.02, "output_including_reasoning": 1.25,
    }
    assert rate["verified_from_official_source"] is True


def test_balance_failure_denies_authorization_without_model_usage():
    checkpoint = _json("data/manifests/p1_v3_runtime_cost_pilot_execution_checkpoint.json")
    balance = checkpoint["platform_balance_check"]
    assert balance["endpoint_requires"] == "OPENAI_ADMIN_KEY"
    assert balance["project_key_read_only_attempt_http_status"] == 403
    assert balance["balance_verified"] is False
    assert balance["model_request_made"] is False and balance["token_usage"] == 0
    assert checkpoint["decision"]["authorization"] == "DENY_PENDING_BALANCE_VERIFICATION"
    assert checkpoint["authorization"]["pilot_execution"] is False


def test_budget_guard_reserves_worst_case_and_fails_closed():
    budget = PilotBudgetController(
        cap_usd=0.001, uncached_input_rate=0.20,
        cached_input_rate=0.02, output_rate=1.25,
    )
    with pytest.raises(RuntimeError, match="could exceed"):
        budget.reserve_or_fail(input_token_upper_bound=1000, output_token_upper_bound=1000)
    safe = PilotBudgetController(
        cap_usd=1.50, uncached_input_rate=0.20,
        cached_input_rate=0.02, output_rate=1.25,
    )
    assert safe.reserve_or_fail(input_token_upper_bound=1000, output_token_upper_bound=2000) < 1.50


def test_checkpoint_audit_hashes_and_zero_workload_boundary():
    audit = _json("data/manifests/p1_v3_runtime_cost_pilot_execution_checkpoint_audit.json")
    for row in audit["dependencies"] + audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])
    assert audit["implementation"]["sha256"] == _hash(audit["implementation"]["path"])
    assert audit["verdict"]["official_rate_verified"] is True
    assert audit["verdict"]["platform_balance_verified"] is False
    assert audit["verdict"]["pilot_execution_authorized"] is False
    boundary = audit["evidence_boundary"]
    assert boundary["model_api_calls"] == 0
    assert boundary["bootstrap_or_boss_runs"] == 0
    assert boundary["semantic_api_calls"] == 0
    assert boundary["pilot_observation_rows_generated"] == 0
    assert boundary["final_holdout_accessed"] is False
