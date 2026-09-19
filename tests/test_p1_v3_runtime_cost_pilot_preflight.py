from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fourgraph.runtime_cost_pilot import PilotAuthorizationError, cost_usd, require_live_authorization


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _jsonl(path: str):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_exact_pilot_ids_blueprints_and_semantic_sample_are_frozen():
    rows = _jsonl("data/manifests/p1_v3_runtime_cost_pilot_inventory.jsonl")
    assert [row["pilot_id"] for row in rows] == [f"SYNPILOT{i:03d}" for i in range(9)]
    assert len({row["blueprint_sha256"] for row in rows}) == 9
    assert sum(row["selected_for_semantic_runtime_sample"] for row in rows) == 6
    assert all(row["task_solver_agreements"] == 5 for row in rows)
    assert all(row["observation_rows_generated"] == 0 for row in rows)
    assert all(row["story_variants_generated"] == 0 for row in rows)


def test_environment_and_secret_boundary_are_pinned():
    env = _json("configs/p1_v3_runtime_cost_pilot_environment.json")
    assert env["python"]["version"] == "3.10.21"
    assert env["java"]["version"] == "21.0.10"
    assert env["java"]["java_on_path"] is False
    assert Path(env["java"]["jvm_path"]).exists()
    assert env["credentials"]["openai_api_key_present"] is True
    assert env["credentials"]["secret_values_captured"] is False
    assert _hash(env["tetrad"]["jar"]) == env["tetrad"]["sha256"]


def test_offline_rate_budget_is_conservative_and_not_misrepresented():
    manifest = _json("data/manifests/p1_v3_runtime_cost_pilot_preflight.json")
    rate = manifest["rate_budget"]["rate_card"]
    assert rate["kind"] == "conservative_offline_accounting_ceiling"
    assert rate["official_current_nano_rate_verified"] is False
    assert manifest["rate_budget"]["budget"]["pilot_hard_cap_usd"] == 1.5
    assert manifest["preflight_gates"]["execution_ready"] is False


def test_cost_formula_and_fail_closed_authorization():
    assert cost_usd(
        input_tokens=1_000_000, cached_input_tokens=100_000, output_tokens=10_000,
        uncached_input_rate=0.75, cached_input_rate=0.075, output_rate=4.50,
    ) == pytest.approx(0.7275)
    with pytest.raises(PilotAuthorizationError, match="explicit user authorization"):
        require_live_authorization(
            {
                "schema_version": "fourgraph.p1_v3_runtime_cost_pilot_live_authorization.v1",
                "preflight_audit_sha256": "ABC", "explicit_user_authorization": False,
                "pilot_execution": False, "successor_cohort_generation": False,
                "final_holdout_access": False,
            },
            "ABC",
        )


def test_audit_hashes_counts_and_no_execution_authorization():
    audit = _json("data/manifests/p1_v3_runtime_cost_pilot_preflight_audit.json")
    for row in audit["dependencies"] + audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])
    assert audit["implementation"]["sha256"] == _hash(audit["implementation"]["path"])
    assert audit["counts"] == {
        "api_calls": 0, "blueprints_replayed": 9, "boss_runs": 0,
        "observation_rows": 0, "pilot_identities": 9, "semantic_sample_ids": 6,
        "stories": 0, "task_solver_agreements": 45,
    }
    assert audit["verdict"]["preflight_frozen"] is True
    assert audit["verdict"]["execution_ready"] is False
    assert audit["authorization"]["pilot_execution"] is False
    assert audit["authorization"]["semantic_api_calls"] is False
    assert audit["authorization"]["final_holdout_access"] is False
