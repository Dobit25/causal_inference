from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

from fourgraph.reasoner import TASKS


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/t12_v3_openai_mini_oracle_dev.yaml"
RUNNER = ROOT / "scripts/run_t12_v3_oracle_development.py"
SPLIT = ROOT / "data/manifests/p0_frozen_split.json"
SCORES = ROOT / "data/manifests/t12_v3_openai_mini_oracle_dev_scores.jsonl"
AUDIT = ROOT / "data/manifests/t12_v3_openai_mini_oracle_dev_audit.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_oracle_development_candidate_is_narrow_and_holdout_closed() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    cohort = split["cohorts"]["primary_downstream"]

    assert config["frozen_benchmark_inputs"]["scene_ids"] == cohort["dev_ids"]
    assert set(config["frozen_benchmark_inputs"]["scene_ids"]).isdisjoint(
        cohort["holdout_ids"]
    )
    assert config["frozen_benchmark_inputs"]["graph_condition"] == "G_ORACLE"
    assert config["frozen_benchmark_inputs"]["expected_records"] == 35
    assert config["live_execution"] == {
        "allowed": True,
        "next_action": "oracle_development_35",
        "full_development_matrix_auto_start_allowed": False,
        "t13_auto_start_allowed": False,
    }
    assert config["holdout"]["accessed"] is False
    assert config["holdout"]["eligible"] is False


def test_oracle_development_frozen_result_passes_registered_gates() -> None:
    rows = _rows(SCORES)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))

    assert len(rows) == 35
    assert len({row["scene_id"] for row in rows}) == 7
    assert Counter(row["task_id"] for row in rows) == Counter(
        {task: 7 for task in TASKS}
    )
    assert all(row["graph_condition"] == "G_ORACLE" for row in rows)
    assert all(row["graph_type"] == "dag" for row in rows)
    assert all(
        row["schema_version"]
        == "fourgraph.t12_v3_oracle_development_score.v1"
        for row in rows
    )

    assert sum(row["oracle_answer_accuracy"] for row in rows) == 34
    assert audit["oracle_answer_correct"] == 34
    assert audit["oracle_answer_accuracy"] == 0.97142857
    assert audit["task_correct"] == {
        "identification__one_valid_adjustment_set": 6,
        "identification__all_minimal_adjustment_sets": 7,
        "identification__minimal_adjustment_set_size": 7,
        "identification__n_valid_adjustment_sets": 7,
        "bias_diagnostic__forbidden_controls_list": 7,
    }
    assert audit["required_empty_sentinel_correct"] == 12
    assert audit["required_empty_sentinel_accuracy"] == 1.0
    assert audit["first_attempt_schema_compliance"] == 35
    assert audit["retry_calls"] == 0
    assert all(audit["gate_results"].values())
    assert audit["oracle_development_passed"] is True
    assert audit["full_development_matrix_eligible"] is True
    assert audit["holdout_reasoner_ready"] is False
    assert audit["holdout_accessed"] is False


def test_oracle_development_artifact_hashes_pin_code_config_and_records() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["config_sha256"] == _sha(CONFIG)
    assert audit["runner_sha256"] == _sha(RUNNER)
    assert audit["records_sha256"] == _sha(SCORES)
