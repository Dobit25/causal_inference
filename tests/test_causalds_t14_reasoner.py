import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_t14_reasoner_has_no_semantic_builder_dependency():
    tree = ast.parse((ROOT / "scripts/run_t14_reasoner.py").read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "fourgraph.causalds_public" not in imports
    assert "fourgraph.llm_graph" not in imports
    assert "fourgraph.hybrid_graph" not in imports
    assert "fourgraph.causalds_scd" not in imports
