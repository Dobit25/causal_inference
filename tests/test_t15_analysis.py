import ast
import json
from pathlib import Path

from fourgraph.t15_analysis import benjamini_hochberg, exact_mcnemar, paired_cluster_bootstrap


ROOT = Path(__file__).resolve().parents[1]


def test_t15_helpers_are_deterministic_and_paired():
    left = {"a": 1.0, "b": 0.5, "c": 0.0}
    right = {"a": 0.0, "b": 0.5, "c": 1.0}
    first = paired_cluster_bootstrap(left, right, replicates=100, root_seed=13015, namespace="test")
    assert first == paired_cluster_bootstrap(left, right, replicates=100, root_seed=13015, namespace="test")
    assert first["paired_scene_count"] == 3
    assert first["effect_left_minus_right"] == 0.0


def test_bh_and_exact_mcnemar():
    assert benjamini_hochberg([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]
    result = exact_mcnemar([True, True, True, False], [False, False, True, False])
    assert result["left_correct_right_incorrect"] == 2
    assert result["left_incorrect_right_correct"] == 0
    assert result["two_sided_exact_p"] == 0.5


def test_t15_is_offline_and_artifacts_are_complete():
    tree = ast.parse((ROOT / "scripts/analyze_t15.py").read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "openai" not in imports
    assert "fourgraph.openai_backend" not in imports
    assert "fourgraph.t10_openai_backend" not in imports
    assert "fourgraph.t12_openai_backend" not in imports
    audit_path = ROOT / "data/manifests/t15_analysis_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        assert audit["verdict"]["t15_complete"] is True
        assert audit["scope"]["api_calls"] == 0
        assert audit["artifacts"]["scene_summaries"]["records"] == 225
        assert audit["artifacts"]["pairwise_results"]["records"] == 36

