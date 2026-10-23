import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_look200_execution_freeze_pins_registered_scope() -> None:
    config = yaml.safe_load(
        (ROOT / "configs/p1_v4_look200_cumulative_oracle_scoring_execution_freeze.yaml").read_text()
    )
    freeze_path = ROOT / config["execution_freeze"]["path"]
    audit_path = ROOT / config["execution_freeze"]["audit_path"]
    freeze = json.loads(freeze_path.read_text())
    audit = json.loads(audit_path.read_text())
    assert freeze["status"] == "PASS_READY_FOR_EXPLICIT_ORACLE_SCORING_AUTHORIZATION"
    assert len(freeze["exact_scene_ids"]) == 200
    assert freeze["scope"]["exact_parent_graphs"] == 400
    assert freeze["scope"]["exact_six_vote_groups"] == 3554
    assert freeze["scope"]["next_registered_look"] == 240
    assert audit["status"] == "PASS"
    assert audit["execution_freeze_sha256"] == digest(freeze_path)


def test_look200_execution_freeze_is_oracle_dark() -> None:
    freeze = json.loads(
        (ROOT / "data/manifests/p1_v4_look200_oracle_scoring_execution_freeze.json").read_text()
    )
    assert freeze["boundary"] == {
        "holdout_access": 0,
        "meek_closure": 0,
        "oracle_access_during_freeze": 0,
        "semantic_api_calls": 0,
        "statistical_reruns": 0,
        "validation_access": 0,
    }
    assert freeze["oracle_scoring_authorized"] is False
    assert freeze["automatic_execution"] is False


def test_look200_scorer_and_inputs_are_hash_pinned() -> None:
    config = yaml.safe_load(
        (ROOT / "configs/p1_v4_look200_cumulative_oracle_scoring_execution_freeze.yaml").read_text()
    )
    assert digest(ROOT / config["implementation"]["scorer"]) == config["implementation"]["scorer_sha256"]
    for spec in config["inputs"].values():
        assert digest(ROOT / spec["path"]) == spec["sha256"]


def test_look200_registered_gates_are_not_relaxed() -> None:
    config = yaml.safe_load(
        (ROOT / "configs/p1_v4_look200_cumulative_oracle_scoring_execution_freeze.yaml").read_text()
    )
    assert config["sequential_gates"]["risk"]["error_ceiling"] == 0.05
    assert config["sequential_gates"]["risk"]["minimum_contributing_scenes"] == 100
    assert config["sequential_gates"]["coverage"]["floor"] == 0.20
    assert config["sequential_gates"]["high_guardrail"]["error_ceiling"] == 0.10
    assert config["sequential_gates"]["high_guardrail"]["minimum_contributing_scenes"] == 60
    assert config["scope"]["automatic_agreements"] == ["VERY_HIGH", "HIGH"]
