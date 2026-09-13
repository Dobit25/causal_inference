import ast
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_t14_graphs.py"


def load_module():
    spec = importlib.util.spec_from_file_location("run_t14_graphs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_t14_preflight_reads_the_exact_frozen_holdout_ids():
    module = load_module()
    manifest, scene_ids = module.validate_t13()
    assert len(scene_ids) == 25
    assert scene_ids == manifest["cohorts"]["graph"]["holdout_scene_ids"]
    assert module.seeded_order(scene_ids, 13014) == module.seeded_order(scene_ids, 13014)
    assert set(module.seeded_order(scene_ids, 13014)) == set(scene_ids)


def test_t14_non_oracle_graph_runner_does_not_import_oracle_or_scoring():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "fourgraph.causalds_oracle" not in imports
    assert "fourgraph.causalds_scoring" not in imports
    assert "fourgraph.reasoner" not in imports
