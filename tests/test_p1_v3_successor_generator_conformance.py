from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
import yaml

from fourgraph.successor_generation import SuccessorGenerationError, allocate_role


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _jsonl(path: str):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_synthetic_suite_cardinality_namespace_and_solver_agreement():
    rows = _jsonl("data/manifests/p1_v3_successor_generator_synthetic.jsonl")
    assert len(rows) == 24
    assert Counter(row["role"] for row in rows) == {"SYNDEV": 8, "SYNCAL": 8, "SYNVAL": 8}
    assert all(row["synthetic_id"].startswith("SYN") for row in rows)
    assert all(row["contract_scene_id"].startswith("synthetic_scene_") for row in rows)
    assert all(row["task_solver_agreements"] == 5 for row in rows)
    assert all(row["observation_rows_generated"] == 0 for row in rows)
    assert sum(row["task_solver_agreements"] for row in rows) == 120


def test_each_synthetic_role_has_exact_registered_margins():
    config = yaml.safe_load(
        (ROOT / "configs/p1_v3_successor_generator_conformance.yaml").read_text(encoding="utf-8")
    )
    expected = config["synthetic_suite"]["role_marginals"]
    rows = _jsonl("data/manifests/p1_v3_successor_generator_synthetic.jsonl")
    mapping = {
        "node_count": "node_count",
        "primary_motif": "assigned_primary_motif",
        "noise_family": "noise_family",
        "query_stratum": "query_target_stratum",
    }
    for role in config["synthetic_suite"]["roles"]:
        role_rows = [row["allocation"] for row in rows if row["role"] == role]
        for feature, field in mapping.items():
            observed = {str(key): value for key, value in Counter(row[field] for row in role_rows).items()}
            wanted = {str(key): value for key, value in expected[feature].items()}
            assert observed == wanted


def test_reserved_real_namespaces_fail_closed():
    marginals = {
        "node_count": {5: 1, 6: 0, 7: 0},
        "primary_motif": {"chain": 1, "fork": 0, "collider": 0, "mediator": 0, "diamond": 0},
        "noise_family": {"laplace": 1, "logistic": 0, "student_t_df5": 0},
        "query_stratum": {
            "valid_empty": 1, "one_minimal_nonempty": 0,
            "multiple_minimal": 0, "no_valid_adjustment_set": 0,
        },
    }
    with pytest.raises(SuccessorGenerationError, match="reserved real namespace"):
        allocate_role(
            role="SYN", namespace="P1V3D", scene_count=1, scene_number_start=1,
            master_seed=1, marginals=marginals,
        )


def test_all_invalid_fixtures_are_rejected():
    rows = _jsonl("data/manifests/p1_v3_successor_generator_invalid.jsonl")
    assert len(rows) == 30 and all(row["rejected"] for row in rows)
    assert len({row["fixture_type"] for row in rows}) == 10


def test_audit_boundary_authorization_and_hashes():
    audit = _json("data/manifests/p1_v3_successor_generator_conformance_audit.json")
    assert audit["counts"] == {
        "deterministic_replays": 24,
        "exact_marginal_checks": 12,
        "invalid_fixtures_rejected": 30,
        "observation_rows_generated": 0,
        "real_design_roles_validated_arithmetic_only": 3,
        "real_successor_ids_materialized": 0,
        "scenes": 24,
        "seed_perturbation_changes": 3,
        "task_solver_agreements": 120,
    }
    assert audit["evidence_boundary"]["bootstrap_or_boss_runs"] == 0
    assert audit["evidence_boundary"]["semantic_api_calls"] == 0
    assert audit["evidence_boundary"]["final_holdout_accessed"] is False
    assert audit["authorization"]["successor_cohort_generation"] is False
    assert audit["authorization"]["runtime_cost_pilot_execution"] is False
    for row in audit["dependencies"] + audit["implementations"] + audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])


def test_real_cohort_design_remains_unmaterialized():
    design = _json("data/manifests/p1_v3_cohort_design.json")
    assert design["cohorts_materialized"] is False
    assert design["scene_ids_materialized"] is False
    assert design["new_scene_count"] == 840
    assert all(
        design["roles"][role]["scenes_generated"] == 0
        for role in ("method_development", "semantic_calibration", "threshold_validation")
    )
