from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from fourgraph.reasoner import TASKS


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/t12_v3_openai_mini_full_development.yaml"
RUNNER = ROOT / "scripts/run_t12_v3_full_development.py"
SPLIT = ROOT / "data/manifests/p0_frozen_split.json"
SCORES = ROOT / "data/manifests/t12_v3_openai_mini_full_dev_scores.jsonl"
AUDIT = ROOT / "data/manifests/t12_v3_openai_mini_full_dev_audit.json"

CONDITIONS = {
    "G_LLM",
    "G_SCD_RAW",
    "G_SCD_PROJECTED",
    "G_HYBRID",
    "G_ORACLE",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_full_development_candidate_is_dev_only_and_has_no_accuracy_gate() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    cohort = split["cohorts"]["primary_downstream"]

    assert config["frozen_benchmark_inputs"]["scene_ids"] == cohort["dev_ids"]
    assert set(cohort["dev_ids"]).isdisjoint(cohort["holdout_ids"])
    assert [item["condition"] for item in config["graph_conditions"]] == [
        "G_LLM",
        "G_SCD_RAW",
        "G_SCD_PROJECTED",
        "G_HYBRID",
        "G_ORACLE",
    ]
    assert config["preflight_expectations"]["records"] == 175
    assert config["full_development_gate"]["accuracy_threshold"] == (
        "none_exploratory_graph_source_comparison"
    )
    assert config["live_execution"]["t13_auto_start_allowed"] is False
    assert config["live_execution"]["holdout_auto_start_allowed"] is False
    assert config["holdout"]["accessed"] is False


def test_full_development_matrix_is_complete_and_canonically_cached() -> None:
    rows = _rows(SCORES)
    assert len(rows) == 175
    assert len({(row["scene_id"], row["task_id"], row["graph_condition"]) for row in rows}) == 175
    assert len({row["scene_id"] for row in rows}) == 7
    assert {row["graph_condition"] for row in rows} == CONDITIONS
    assert Counter((row["graph_condition"], row["task_id"]) for row in rows) == Counter(
        {(condition, task): 7 for condition in CONDITIONS for task in TASKS}
    )
    assert all(
        row["schema_version"] == "fourgraph.t12_v3_full_development_score.v1"
        for row in rows
    )

    by_key: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_key[row["cache_key"]].append(row)
    assert len(by_key) == 105
    assert all(len({row["raw_response_sha256"] for row in group}) == 1 for group in by_key.values())
    assert sum(len(group) - 1 for group in by_key.values()) == 70
    assert all(
        row["response_origin"] == "inherited_oracle_development"
        for row in rows
        if row["graph_condition"] == "G_ORACLE"
    )


def test_full_development_result_passes_integrity_gates_and_freezes_reasoner() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["records"] == 175
    assert audit["unique_canonical_inputs"] == 105
    assert audit["canonical_reused_records"] == 70
    assert audit["inherited_oracle_response_matches"] == 35
    assert audit["first_attempt_schema_compliance"] == 175
    assert audit["captured_inherited_calls"] == 35
    assert audit["captured_incremental_calls"] == 70
    assert audit["incremental_retry_calls"] == 0
    assert audit["incomplete_calls"] == 0
    assert all(audit["gate_results"].values())
    assert audit["full_development_matrix_passed"] is True
    assert audit["reasoner_frozen_for_holdout"] is True
    assert audit["holdout_reasoner_ready"] is True
    assert audit["t13_eligible"] is True
    assert audit["holdout_accessed"] is False

    assert audit["condition_summary"]["G_ORACLE"]["oracle_answer_correct"] == 34
    assert audit["condition_summary"]["G_LLM"]["oracle_answer_correct"] == 33
    assert audit["condition_summary"]["G_HYBRID"]["oracle_answer_correct"] == 31
    assert audit["condition_summary"]["G_SCD_PROJECTED"]["oracle_answer_correct"] == 6
    assert audit["condition_summary"]["G_SCD_RAW"]["oracle_answer_correct"] == 4


def test_full_development_artifact_hashes_pin_code_config_and_records() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["config_sha256"] == _sha(CONFIG)
    assert audit["runner_sha256"] == _sha(RUNNER)
    assert audit["records_sha256"] == _sha(SCORES)
