import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from fourgraph.p1_generation import seed64


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data/manifests/t18_p1_scene_inventory.jsonl"
SPLIT = ROOT / "data/manifests/t18_p1_frozen_split.json"
TASKS = ROOT / "data/manifests/t18_p1_task_manifest.jsonl"
AUDIT = ROOT / "data/manifests/t18_p1_generation_audit.json"
SHA256 = re.compile(r"^[0-9A-F]{64}$")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_t18_builder_has_no_provider_sdk_dependency():
    modules = [ROOT / "scripts/build_p1_t18.py", ROOT / "src/fourgraph/p1_generation.py"]
    imported: set[str] = set()
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        imported.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not {name for name in imported if name == "openai" or name.startswith("google.genai")}


def test_t18_config_preserves_the_frozen_execution_boundary():
    config = yaml.safe_load((ROOT / "configs/t18_p1_generation.yaml").read_text(encoding="utf-8"))
    assert config["randomness"]["master_seed"] == 1701
    assert config["observations"]["primary_n"] == 2000
    assert config["observations"]["sensitivity_n"] == [500, 10000]
    assert config["tasks"]["required_agreement"] == "500_of_500"
    assert config["split"]["development_count"] == 20
    assert config["split"]["holdout_count"] == 80
    boundary = config["access_boundary"]
    assert boundary["api_calls"] == 0
    assert boundary["llm_imports_allowed"] is False
    assert boundary["H2_implementation_authorized"] is False
    assert boundary["holdout_method_evaluation_authorized"] is False
    assert boundary["holdout_downstream_scoring_authorized"] is False


def test_t18_inventory_has_exact_balanced_eligible_scene_population():
    rows = _jsonl(INVENTORY)
    assert len(rows) == 100
    assert [row["study_id"] for row in rows] == [f"P1S{i:03d}" for i in range(100)]
    assert [row["scene_id"] for row in rows] == [f"scene_{100000 + i:06d}" for i in range(100)]
    assert Counter(row["node_count"] for row in rows) == {5: 34, 6: 33, 7: 33}
    assert Counter(row["assigned_primary_motif"] for row in rows) == {
        "chain": 20,
        "fork": 20,
        "collider": 20,
        "mediator": 20,
        "diamond": 20,
    }
    assert Counter(row["exogenous_noise_family"] for row in rows) == {
        "laplace": 34,
        "logistic": 33,
        "student_t_df5": 33,
    }
    assert Counter(row["query_target_stratum"] for row in rows) == {
        "valid_empty": 25,
        "one_minimal_nonempty": 25,
        "multiple_minimal": 25,
        "no_valid_adjustment_set": 25,
    }
    assert all(row["connected"] for row in rows)
    assert all(row["latent_node_count"] == 0 for row in rows)
    assert all(row["variable_types"] == ["continuous"] for row in rows)
    assert all(row["assigned_primary_motif"] in row["verified_motifs"] for row in rows)
    assert all(row["oracle_cpdag_unresolved_edges"] >= 2 for row in rows)
    assert all(row["task_count"] == 5 for row in rows)
    assert Counter(row["split"] for row in rows) == {"development": 20, "holdout": 80}
    assert Counter(row["sensitivity_scene"] for row in rows) == {False: 80, True: 20}
    for row in rows:
        expected_sizes = [500, 2000, 10000] if row["sensitivity_scene"] else [2000]
        assert row["observation_sample_sizes"] == expected_sizes


def test_t18_split_is_exact_nested_and_balanced():
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    development = split["development_ids"]
    holdout = split["holdout_ids"]
    assert len(development) == 20
    assert len(holdout) == 80
    assert not set(development) & set(holdout)
    assert set(development) | set(holdout) == {f"P1S{i:03d}" for i in range(100)}
    assert len(split["sensitivity_development_ids"]) == 4
    assert len(split["sensitivity_holdout_ids"]) == 16
    assert set(split["sensitivity_development_ids"]) <= set(development)
    assert set(split["sensitivity_holdout_ids"]) <= set(holdout)
    assert split["stratification"]["maximum_rounded_marginal_count_deviation"] <= 2
    mapping = split["study_to_contract_scene_id"]
    assert len(mapping) == 100
    assert all(item["scene_id"] == f"scene_{100000 + int(item['study_id'][-3:]):06d}" for item in mapping)
    assert split["method_outputs_used"] == []


def test_t18_public_task_manifest_has_five_tasks_per_scene_without_gold_answers():
    rows = _jsonl(TASKS)
    expected_tasks = {
        "identification__one_valid_adjustment_set",
        "identification__all_minimal_adjustment_sets",
        "identification__minimal_adjustment_set_size",
        "identification__n_valid_adjustment_sets",
        "bias_diagnostic__forbidden_controls_list",
    }
    by_scene: dict[str, set[str]] = defaultdict(set)
    assert len(rows) == 500
    for row in rows:
        by_scene[row["study_id"]].add(row["task_id"])
        assert row["gold_answer_in_versioned_manifest"] is False
        assert "expected" not in row
        assert "accepted" not in row
        assert SHA256.fullmatch(row["expected_target_sha256"])
        assert SHA256.fullmatch(row["grading_record_sha256"])
        assert SHA256.fullmatch(row["query_sha256"])
    assert len(by_scene) == 100
    assert all(task_ids == expected_tasks for task_ids in by_scene.values())


def test_t18_audit_pins_outputs_and_records_all_gates():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["counts"]["scenes"] == 100
    assert audit["counts"]["tasks"] == 500
    assert audit["counts"]["production_independent_solver_agreements"] == 500
    assert audit["raw_artifact_tree"]["file_count"] == 480
    assert audit["generation_diagnostics"]["nested_prefix_transitions_checked"] == 40
    assert audit["generation_diagnostics"]["standardized_arrays_checked"] == 140
    assert audit["evidence_boundary"]["api_calls"] == 0
    assert audit["evidence_boundary"]["provider_SDK_imported_or_called"] is False
    assert audit["evidence_boundary"]["H2_implemented_or_executed"] is False
    assert audit["evidence_boundary"]["holdout_method_results_accessed"] is False
    assert audit["evidence_boundary"]["holdout_downstream_scored"] is False
    assert audit["verdict"]["t18_complete"] is True
    assert audit["verdict"]["generator_reproducible"] is True
    assert audit["verdict"]["solver_agreement_500_of_500"] is True
    assert audit["verdict"]["t19_story_generation_authorized"] is True
    assert audit["verdict"]["live_model_calls_authorized"] is False
    output_by_path = {item["path"]: item for item in audit["outputs"]}
    for relative in (
        "data/manifests/t18_p1_scene_inventory.jsonl",
        "data/manifests/t18_p1_frozen_split.json",
        "data/manifests/t18_p1_task_manifest.jsonl",
        "reports/t18_p1_generation.md",
    ):
        path = ROOT / relative
        assert output_by_path[relative]["bytes"] == path.stat().st_size
        assert output_by_path[relative]["sha256"] == _sha256(path)


def test_t18_seed_derivation_is_deterministic_and_component_separated():
    assert seed64(1701, "P1S000", "observations") == seed64(1701, "P1S000", "observations")
    assert seed64(1701, "P1S000", "observations") != seed64(1701, "P1S000", "edge_weights")
    assert seed64(1701, "P1S000", "observations") != seed64(1701, "P1S001", "observations")
