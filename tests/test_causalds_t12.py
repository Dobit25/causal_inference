from __future__ import annotations

import json
from pathlib import Path

import yaml

from fourgraph.graph_contract import GraphArtifact, VariableMap
from fourgraph.reasoner import TASKS


ROOT = Path(__file__).resolve().parents[1]


def _rows(path: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines() if line]


def test_t12_config_freezes_reasoner_and_evidence_boundary() -> None:
    config = yaml.safe_load((ROOT / "configs/t12_reasoner.yaml").read_text(encoding="utf-8"))
    reasoner = config["reasoner"]
    assert reasoner["provider"] == "google_ai_studio"
    assert reasoner["model_id"] == reasoner["model_version"] == "gemma-4-31b-it"
    assert reasoner["temperature"] == 0
    boundary = config["evidence_contract"]
    assert boundary["glossary"] == "canonical_id_and_type_only"
    assert boundary["allow_public_semantic_names"] is False
    assert boundary["allow_story"] is False
    assert boundary["allow_observational_table"] is False
    assert boundary["allow_graph_provenance"] is False
    assert boundary["allow_gold_answer"] is False


def test_t12_versioned_records_are_complete_and_hash_linked() -> None:
    rows = _rows("data/manifests/t12_dev_reasoner_scores.jsonl")
    assert len(rows) == 175
    assert len({(r["scene_id"], r["task_id"], r["graph_condition"]) for r in rows}) == 175
    assert {r["task_id"] for r in rows} == set(TASKS)
    assert {r["graph_condition"] for r in rows} == {
        "G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID", "G_ORACLE"
    }
    assert all(r["provider"] == "google_ai_studio" for r in rows)
    assert all(r["model_version"] == "gemma-4-31b-it" for r in rows)
    assert all(isinstance(r["oracle_answer_accuracy"], bool) for r in rows)
    assert all(isinstance(r["uncertainty_aware_correctness"], bool) for r in rows)
    assert sum(r["uncertainty_target"]["status"] == "undetermined" for r in rows) == 31


def test_t12_audit_records_holdout_gate_honestly() -> None:
    audit = json.loads((ROOT / "data/manifests/t12_reasoner_audit.json").read_text(encoding="utf-8"))
    assert audit["t12_complete"] is True
    assert audit["fixed_reasoner_contract_ready"] is True
    assert audit["holdout_reasoner_ready"] is False
    assert audit["holdout_accessed"] is False
    assert audit["records"] == audit["expected_records"] == 175
    assert audit["invalid_responses"] == 0


def test_reasoner_graph_payload_and_glossary_exclude_provenance_and_names() -> None:
    graph = GraphArtifact.from_dict(_rows("data/manifests/t08_dev_graphs.jsonl")[0])
    payload = graph.reasoner_view()
    assert set(payload) == {"schema_version", "graph_type", "nodes", "edges"}
    mapping = VariableMap.build(
        graph.scene_id,
        [(f"semantic secret {index}", "continuous") for index in range(len(graph.nodes))],
    )
    text = json.dumps(mapping.reasoner_glossary())
    assert "semantic secret" not in text
    assert "public_name" not in text
