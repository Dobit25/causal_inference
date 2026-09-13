import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_t14_metric_stage_cannot_call_llm_or_read_tasks():
    tree = ast.parse((ROOT / "scripts/evaluate_t14_graph_metrics.py").read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "fourgraph.openai_backend" not in imports
    assert "fourgraph.t10_openai_backend" not in imports
    assert "fourgraph.t12_openai_backend" not in imports
    assert "fourgraph.causalds_scoring" not in imports
    assert "fourgraph.reasoner" not in imports
