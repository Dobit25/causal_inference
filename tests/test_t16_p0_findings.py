import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_t16_finalizer_is_offline():
    tree = ast.parse((ROOT / "scripts/finalize_t16_p0.py").read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "openai" not in imports
    assert "fourgraph.openai_backend" not in imports
    assert "fourgraph.t10_openai_backend" not in imports
    assert "fourgraph.t12_openai_backend" not in imports


def test_t16_decision_is_refine_without_p1_execution_authority():
    path = ROOT / "data/manifests/t16_p0_findings_audit.json"
    if not path.exists():
        return
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["verdict"]["t16_complete"] is True
    assert audit["verdict"]["p0_complete"] is True
    assert audit["verdict"]["p0_decision"] == "REFINE"
    assert audit["verdict"]["p1_started"] is False
    assert audit["verdict"]["p1_execution_authorized"] is False
    assert audit["evidence_boundary"]["api_calls"] == 0

