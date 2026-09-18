from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _jsonl(path: str):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines()]


def _hash(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper()


def test_conformance_covers_registered_regimes_nodes_and_grid():
    rows = _jsonl("data/manifests/p1_v3_bootstrap_boss_conformance.jsonl")
    assert len(rows) == 60
    assert {row["regime"] for row in rows} == {
        "stable_undirected", "unstable_adjacency", "stable_A_to_B",
        "stable_B_to_A", "direction_conflict", "usually_absent",
    }
    assert {row["node_count"] for row in rows} == {3, 4, 5, 6, 7}
    assert all(row["bootstrap_runs"] == 200 for row in rows)
    assert all(len(row["threshold_decisions"]) == 15 for row in rows)
    assert all(row["production_reference_agreement"] for row in rows)
    assert all(row["run_order_invariant"] and row["node_input_order_normalized"] for row in rows)


def test_target_edge_rates_match_counts_and_use_all_200_runs():
    rows = _jsonl("data/manifests/p1_v3_bootstrap_boss_conformance.jsonl")
    for row in rows:
        counts = row["target_counts"]
        rates = row["target_rates"]
        assert sum(counts.values()) == 200
        for state in ("absent", "undirected", "A_to_B", "B_to_A"):
            assert rates[state] == counts[state] / 200
        assert rates["adjacency_stability"] == 1 - rates["absent"]


def test_audit_records_complete_offline_agreement_and_sealed_boundary():
    audit = _json("data/manifests/p1_v3_bootstrap_boss_conformance_audit.json")
    assert audit["counts"] == {
        "bootstrap_graph_states_aggregated": 12000,
        "input_immutability_passes": 60,
        "invalid_fixtures_rejected": 30,
        "node_input_order_normalization_passes": 60,
        "production_reference_aggregate_agreements": 60,
        "production_reference_parent_agreements": 900,
        "run_order_invariance_passes": 60,
        "synthetic_cases": 60,
        "threshold_parent_decisions": 900,
    }
    assert audit["evidence_boundary"]["tetrad_or_boss_execution"] is False
    assert audit["evidence_boundary"]["study_observations_loaded"] is False
    assert audit["evidence_boundary"]["semantic_api_calls"] == 0
    assert audit["evidence_boundary"]["final_holdout_accessed"] is False
    assert audit["verdict"]["study_scene_bootstrap_execution_authorized"] is False
    assert audit["verdict"]["successor_cohort_generation_authorized"] is False


def test_invalid_fixtures_all_fail_closed():
    rows = _jsonl("data/manifests/p1_v3_bootstrap_boss_invalid.jsonl")
    assert len(rows) == 30
    assert all(row["rejected"] is True and row["error"] for row in rows)
    assert {row["fixture_type"] for row in rows} == {
        "missing_run", "duplicate_index", "node_mismatch", "non_cpdag",
        "corrupt_hash", "corrupt_count",
    }


def test_audit_dependencies_and_outputs_are_hash_correct():
    audit = _json("data/manifests/p1_v3_bootstrap_boss_conformance_audit.json")
    for row in audit["dependencies"]:
        assert row["sha256"] == _hash(row["path"])
    for row in audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])
        assert row["bytes"] == (ROOT / row["path"]).stat().st_size


def test_intermediate_contract_schemas_are_closed_and_versioned():
    for path in (
        "schemas/bootstrap_boss_aggregate_v1.schema.json",
        "schemas/bootstrap_boss_parent_v1.schema.json",
    ):
        schema = _json(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
