"""Guard the two scientific failure modes of the supplemental design freeze."""
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import freeze_p1_v4_partial_high_supplemental80 as supplement


def test_freeze_keeps_terminal_decision_and_sealed_cohorts():
    audit = json.loads((ROOT / "data/manifests/p1_v4_partial_high_supplemental80_freeze_audit.json").read_text())
    inference = json.loads((ROOT / "data/manifests/p1_v4_partial_high_supplemental80_inference_audit.json").read_text())
    plan = json.loads((ROOT / "data/manifests/p1_v4_partial_high_supplemental80_exact_identity_plan.json").read_text())
    frozen = json.loads((ROOT / "data/manifests/p1_v4_partial_high_supplemental80_protocol.json").read_text())
    assert audit["status"] == "PASS_OFFLINE_FREEZE"
    assert all(audit["identity_checks"].values())
    assert inference["original_look440_decision"] == "STOP_FOR_FUTILITY"
    assert inference["new_high_scenes_needed"] == 7
    assert len(plan["exact_scene_ids_in_execution_order"]) == 80
    assert frozen["boundaries"]["semantic_api_calls"] == 0
    assert frozen["boundaries"]["new_oracle_access"] == 0
    assert frozen["boundaries"]["validation_data_access"] == 0
    assert frozen["boundaries"]["holdout_data_access"] == 0
    artifacts, replay = supplement.build()
    assert replay == audit
    assert all(path.read_bytes() == body for path, body in artifacts.items())


def test_historical_hash_drift_prevents_re_freeze(tmp_path, monkeypatch):
    config = yaml.safe_load(supplement.CFG.read_text(encoding="utf-8"))
    config["historical_inputs"]["review"]["sha256"] = "0" * 64
    altered = tmp_path / "altered_protocol.yaml"
    altered.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(supplement, "CFG", altered)
    with pytest.raises(RuntimeError, match="historical review hash drift"):
        supplement.build()
