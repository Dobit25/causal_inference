import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_scoped_live_authorization_keeps_semantic_oracle_and_holdout_closed() -> None:
    checkpoint = json.loads((ROOT / "data/manifests/p1_v4_stage3_live_authorization_checkpoint.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "data/manifests/p1_v4_stage3_live_authorization_checkpoint_audit.json").read_text(encoding="utf-8"))
    assert checkpoint["status"] == audit["status"] == "PASS_SCOPED_LIVE_AUTHORIZATION"
    assert all(checkpoint["checks"].values())
    assert checkpoint["workload"] == {"materialized_scenes": 30, "statistical_fits": 6180, "semantic_logical_calls_reserved_not_authorized": 360}
    assert checkpoint["authorization"]["materialization_authorized"] is True
    assert checkpoint["authorization"]["statistical_execution_authorized"] is True
    assert checkpoint["authorization"]["semantic_api_calls_authorized"] is False
    assert checkpoint["authorization"]["oracle_access_authorized"] is False
    assert checkpoint["authorization"]["holdout_access_authorized"] is False
