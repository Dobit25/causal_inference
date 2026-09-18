from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _jsonl(path: str):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]


def test_v3c_audit_passes_and_keeps_execution_boundary_closed():
    audit = _json("data/manifests/t21_v3c_validation_generation_audit.json")
    assert audit["verdict"] == {
        "SCD_H1_H2_reasoner_executed": False,
        "api_calls": 0,
        "deterministic_replay_required": True,
        "existing_development_artifacts_accessed": 0,
        "existing_holdout_artifacts_accessed": 0,
        "final_holdout_access_authorized": False,
        "semantic_model_executed": False,
        "story_truth_audit_passed": True,
        "t21_v3c_complete": True,
        "t21_v3d_authorized": True,
        "task_solver_agreement_passed": True,
        "threshold_selected": False,
        "validation_cohort_frozen": True,
        "validation_scenes_generated": 20,
    }
    assert audit["counts"]["tasks"] == audit["counts"]["task_solver_agreements"] == 100
    assert audit["counts"]["stories"] == 60
    assert audit["raw_artifact_tree"]["file_count"] == 180


def test_v3c_exact_namespace_and_no_existing_cohort_overlap():
    cohort = _json("data/manifests/t21_v3c_validation_cohort.json")
    assert cohort["study_ids"] == [f"P1V{i:03d}" for i in range(20)]
    assert cohort["scene_ids"] == [f"scene_{110000+i:06d}" for i in range(20)]
    assert cohort["existing_development_overlap"] == []
    assert cohort["existing_holdout_overlap"] == []
    assert cohort["final_holdout_eligible"] is False
    assert all(not value.startswith("P1S") for value in cohort["study_ids"])
    assert all(not 100000 <= int(value.split("_")[1]) <= 100099 for value in cohort["scene_ids"])


def test_v3c_allocations_inventory_and_uncertainty_match_protocol():
    rows = _jsonl("data/manifests/t21_v3c_validation_inventory.jsonl")
    assert len(rows) == 20
    assert Counter(row["node_count"] for row in rows) == {5: 7, 6: 7, 7: 6}
    assert Counter(row["assigned_primary_motif"] for row in rows) == {
        "chain": 4, "fork": 4, "collider": 4, "mediator": 4, "diamond": 4
    }
    assert Counter(row["exogenous_noise_family"] for row in rows) == {
        "laplace": 7, "logistic": 7, "student_t_df5": 6
    }
    assert Counter(row["query_target_stratum"] for row in rows) == {
        "valid_empty": 5, "one_minimal_nonempty": 5,
        "multiple_minimal": 5, "no_valid_adjustment_set": 5,
    }
    assert all(row["oracle_cpdag_unresolved_edges"] >= 2 for row in rows)
    assert all(row["latent_node_count"] == 0 and row["observation_sample_sizes"] == [2000] for row in rows)
    assert all(len(row["artifacts"]) == 9 for row in rows)
    assert all(item["path"].startswith("data/generated/p1_hybrid_v2/t21_v3c/P1V") for row in rows for item in row["artifacts"])


def test_v3c_public_manifests_do_not_persist_gold_or_story_text():
    tasks = _jsonl("data/manifests/t21_v3c_validation_tasks.jsonl")
    stories = _jsonl("data/manifests/t21_v3c_validation_stories.jsonl")
    aliases = _jsonl("data/manifests/t21_v3c_validation_aliases.jsonl")
    assert len(tasks) == 100 and all(row["solver_agreement"] for row in tasks)
    assert all("expected" not in row and row["gold_answer_persisted"] is False for row in tasks)
    assert len(stories) == 60
    assert Counter(row["variant"] for row in stories) == {"full": 20, "partial": 20, "ambiguous": 20}
    assert all("story" not in row and row["story_text_persisted"] is False for row in stories)
    assert len(aliases) == 20
    assert all("mapping" not in row and row["public_aliases_persisted"] is False for row in aliases)


def test_v3c_builder_has_no_provider_or_existing_raw_access_path():
    source = (ROOT / "scripts/build_t21_v3c_validation.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "from openai", "import openai", "google.genai", "gemini_api_key", "openai_api_key",
        "_json(root / \"data/generated/p1_hybrid_v1", "read_bytes(root / \"data/generated/p1_hybrid_v1",
    )
    assert all(token not in source for token in forbidden)


def test_v3c_replays_byte_for_byte():
    result = subprocess.run(
        [sys.executable, "scripts/build_t21_v3c_validation.py", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"api_calls": 0' in result.stdout
