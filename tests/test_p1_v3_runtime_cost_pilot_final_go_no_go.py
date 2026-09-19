from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fourgraph.runtime_cost_pilot import PilotAuthorizationError, require_live_authorization


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_go_ready_scope_and_all_blocking_gates():
    record = _json("data/manifests/p1_v3_runtime_cost_pilot_final_go_no_go.json")
    assert record["decision"]["outcome"] == "GO_READY"
    assert record["gate_matrix"]["all_blocking_gates_pass"] is True
    assert record["frozen_scope"]["generator_scenes"] == 9
    assert record["frozen_scope"]["boss_measured_fits"] == 270
    assert record["frozen_scope"]["semantic_logical_calls"] == 108
    assert record["frozen_scope"]["pilot_cost_cap_usd"] == 1.5


def test_go_ready_is_not_live_execution_authorization():
    record = _json("data/manifests/p1_v3_runtime_cost_pilot_final_go_no_go.json")
    assert record["decision"]["execution_started"] is False
    assert record["decision"]["automatic_execution"] is False
    assert record["decision"]["pilot_execution_authorized_by_this_checkpoint"] is False
    assert record["authorization_after_freeze"]["execution_eligibility"] is True
    assert record["authorization_after_freeze"]["pilot_execution"] is False
    with pytest.raises(PilotAuthorizationError):
        require_live_authorization(
            record["live_authorization"],
            record["live_authorization"]["preflight_audit_sha256"],
        )


def test_go_no_go_audit_hashes_and_zero_execution_boundary():
    audit = _json("data/manifests/p1_v3_runtime_cost_pilot_final_go_no_go_audit.json")
    for row in audit["dependencies"] + audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])
    assert audit["implementation"]["sha256"] == _hash(audit["implementation"]["path"])
    assert audit["verdict"]["decision"] == "GO_READY"
    assert audit["verdict"]["execution_eligibility"] is True
    assert audit["verdict"]["pilot_execution_authorized_by_checkpoint"] is False
    assert audit["verdict"]["execution_started"] is False
    boundary = audit["evidence_boundary"]
    assert boundary["model_api_calls"] == 0
    assert boundary["bootstrap_or_boss_runs"] == 0
    assert boundary["semantic_api_calls"] == 0
    assert boundary["final_holdout_accessed"] is False
