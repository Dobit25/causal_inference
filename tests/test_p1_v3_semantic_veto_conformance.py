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


def test_semantic_suite_covers_variants_patterns_and_reference_agreement():
    rows = _jsonl("data/manifests/p1_v3_semantic_agreement_conformance.jsonl")
    assert len(rows) == 90
    assert {row["story_variant"] for row in rows} == {"full", "partial", "ambiguous"}
    assert len({pattern for row in rows for pattern in row["patterns"]}) == 10
    assert sum(len(row["semantic_records"]) for row in rows) == 180
    assert all(row["production_reference_agreement"] for row in rows)
    assert {record["agreement_class"] for row in rows for record in row["semantic_records"]} == {
        "very_high", "high", "medium", "uncertain", "conflict"
    }


def test_reliability_records_are_diagnostic_and_false_adjacency_aware():
    rows = _jsonl("data/manifests/p1_v3_empirical_reliability_conformance.jsonl")
    assert len(rows) == 9
    assert all(row["total"] == 30 and row["independent_scenes"] == 30 for row in rows)
    assert all(row["false_adjacencies_count_as_errors"] is True for row in rows)
    assert all(row["certification_status"] == "pending_risk_control" for row in rows)
    assert all(row["diagnostic_wilson_lower_95"] <= row["point_estimate"] for row in rows)


def test_veto_table_agrees_and_never_orients_weak_edges():
    rows = _jsonl("data/manifests/p1_v3_statistical_veto_conformance.jsonl")
    assert len(rows) == 36
    assert all(row["production_reference_agreement"] for row in rows)
    weak = [row for row in rows if row["statistical_status"] in ("weak_adjacency", "absent")]
    assert len(weak) == 12
    assert all(row["decision"]["decision"] == "excluded" for row in weak)
    pending = [row for row in rows if row["semantic_scenario"] == "pending_A"]
    uncertain = [row for row in pending if row["statistical_status"] == "direction_uncertain"]
    assert uncertain[0]["decision"]["decision"] == "undirected"


def test_invalid_responses_all_fail_closed():
    rows = _jsonl("data/manifests/p1_v3_semantic_invalid.jsonl")
    assert len(rows) == 48 and all(row["rejected"] for row in rows)
    assert len({row["fixture_type"] for row in rows}) == 8


def test_audit_boundary_counts_hashes_and_authorization():
    audit = _json("data/manifests/p1_v3_semantic_veto_conformance_audit.json")
    assert audit["counts"] == {
        "invalid_responses_rejected": 48,
        "production_reference_veto_agreements": 36,
        "production_reference_vote_agreements": 180,
        "reliability_count_agreements": 9,
        "reliability_groups": 9,
        "reliability_outcomes": 270,
        "semantic_cases": 90,
        "semantic_edge_records": 180,
        "valid_directional_evidence_quotes": 810,
        "valid_undetermined_null_evidence_records": 270,
        "veto_decisions": 36,
    }
    assert audit["evidence_boundary"]["model_or_api_calls"] == 0
    assert audit["evidence_boundary"]["bootstrap_or_boss_runs"] == 0
    assert audit["evidence_boundary"]["final_holdout_accessed"] is False
    assert audit["verdict"]["reliability_self_certification_allowed"] is False
    assert audit["authorization"]["successor_cohort_generation"] is False
    for row in audit["dependencies"]:
        assert row["sha256"] == _hash(row["path"])
    for row in audit["outputs"]:
        assert row["sha256"] == _hash(row["path"])
        assert row["bytes"] == (ROOT / row["path"]).stat().st_size


def test_new_contract_schemas_are_closed():
    for path in (
        "schemas/empirical_reliability_v1.schema.json",
        "schemas/statistical_veto_decision_v1.schema.json",
    ):
        schema = _json(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object" and schema["additionalProperties"] is False
