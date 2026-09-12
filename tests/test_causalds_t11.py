import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t11_versioned_artifacts_are_complete_and_type_aware():
    audit = json.loads((ROOT / "data/manifests/t11_graph_metrics_audit.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (ROOT / "data/manifests/t11_dev_graph_metrics.jsonl").read_text(encoding="utf-8").splitlines()]
    assert audit["verdict"]["t11_complete"] is True
    assert len(records) == 40
    assert {record["graph_condition"] for record in records} == {"G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID", "G_ORACLE"}
    assert all((record["cpdag"] is not None) == (record["graph_condition"] == "G_SCD_RAW") for record in records)
    assert all((record["hybrid_attribution"] is not None) == (record["graph_condition"] == "G_HYBRID") for record in records)
    assert all(record["functional"][metric]["value"] is None for record in records for metric in ("sid", "aid"))


def test_t11_scope_and_freeze_claims_are_explicit():
    audit = json.loads((ROOT / "data/manifests/t11_graph_metrics_audit.json").read_text(encoding="utf-8"))
    assert audit["scope"]["holdout_accessed"] is False
    assert audit["scope"]["llm_calls_made"] == 0
    assert audit["scope"]["tasks_or_queries_accessed"] is False
    assert audit["scope"]["builder_tuning_performed"] is False
    assert audit["scope"]["oracle_edges_persisted"] is False
    assert all(
        value is True
        for key, value in audit["freeze_checks"].items()
        if key != "t08_t09_t10_artifacts_modified"
    )
    assert audit["freeze_checks"]["t08_t09_t10_artifacts_modified"] is False


def test_t11_evaluator_has_no_builder_or_task_dependency():
    tree = ast.parse((ROOT / "scripts/evaluate_causalds_t11.py").read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = {"fourgraph.openai_backend", "fourgraph.t10_openai_backend", "fourgraph.llm_graph", "fourgraph.hybrid_graph", "fourgraph.scd_graph"}
    assert imports.isdisjoint(forbidden)
