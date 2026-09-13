import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_t14_versioned_audit_is_complete_without_aggregate_analysis():
    audit = json.loads((ROOT / "data/manifests/t14_holdout_execution_audit.json").read_text(encoding="utf-8"))
    assert audit["verdict"] == {"all_scheduled_identities_terminal": True, "replay_ready": True, "t14_complete": True, "t15_authorized": True, "t15_started": False}
    assert audit["scope"]["supplementary_reasoner_records"] == 0
    assert audit["graph_metrics"]["oracle_edges_persisted"] is False
    assert audit["evidence_boundary"]["aggregate_ranking_computed"] is False
    assert audit["evidence_boundary"]["bootstrap_or_bh_performed"] is False


def test_t14_final_auditor_cannot_call_models_or_load_source_data():
    tree = ast.parse((ROOT / "scripts/audit_t14_execution.py").read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert all(not name.startswith("fourgraph.causalds_") for name in imports)
    assert all("openai" not in name for name in imports)
