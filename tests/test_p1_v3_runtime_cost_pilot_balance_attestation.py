from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_attested_budget_arithmetic_and_headroom():
    record = _json("data/manifests/p1_v3_runtime_cost_pilot_balance_attestation.json")
    att = record["attestation"]
    assert att["project_spend_limit_usd"] - att["current_project_spend_usd"] == 9.48
    assert att["calculated_headroom_usd"] == 9.48
    assert record["budget_gate"]["pilot_hard_cap_usd"] == 1.5
    assert record["budget_gate"]["headroom_to_cap_ratio"] == 6.32


def test_hard_limit_risk_and_no_self_authorization():
    record = _json("data/manifests/p1_v3_runtime_cost_pilot_balance_attestation.json")
    assert record["attestation"]["hard_limit_enforced"] is False
    assert record["budget_gate"]["platform_hard_limit_warning"] is True
    assert record["budget_gate"]["internal_budget_controller_required"] is True
    assert record["readiness"]["technical_budget_gate_passed"] is True
    assert record["readiness"]["execution_authorized"] is False
    assert record["authorization_after_freeze"]["pilot_execution"] is False


def test_attestation_audit_hashes_and_zero_execution():
    audit = _json("data/manifests/p1_v3_runtime_cost_pilot_balance_attestation_audit.json")
    for row in audit["dependencies"] + audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])
    assert audit["implementation"]["sha256"] == _hash(audit["implementation"]["path"])
    assert audit["verdict"]["technical_budget_gate_passed"] is True
    assert audit["verdict"]["pilot_execution_authorized"] is False
    assert audit["evidence_boundary"]["model_api_calls"] == 0
    assert audit["evidence_boundary"]["bootstrap_or_boss_runs"] == 0
