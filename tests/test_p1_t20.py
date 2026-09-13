import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
VALID = ROOT / "data/manifests/t20_h2_valid_conformance.jsonl"
INVALID = ROOT / "data/manifests/t20_h2_invalid_conformance.jsonl"
AUDIT = ROOT / "data/manifests/t20_h2_conformance_audit.json"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_t20_code_has_no_provider_or_p1_data_loader_dependency():
    paths = (
        ROOT / "src/fourgraph/hybrid_h2.py",
        ROOT / "src/fourgraph/h2_reference.py",
        ROOT / "scripts/build_t20_h2_conformance.py",
    )
    imports: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports.update(node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name == "openai" or name.startswith("google.genai") or "openai_backend" in name for name in imports)
    script = (ROOT / "scripts/build_t20_h2_conformance.py").read_text(encoding="utf-8")
    assert "data/generated/p1_hybrid_v1/t18" not in script
    assert "data/generated/p1_hybrid_v1/t19" not in script


def test_t20_config_freezes_suite_and_forbids_study_execution():
    config = yaml.safe_load((ROOT / "configs/t20_h2_conformance.yaml").read_text(encoding="utf-8"))
    assert config["conformance"]["valid_cases"] == 150
    assert config["conformance"]["invalid_cases"] == 30
    assert config["conformance"]["selective_decisions"] == 3000
    assert config["h2_selective"]["threshold_grid"]["tau_margin"] == [0.0, 0.02, 0.05, 0.1, 0.2]
    assert config["h2_selective"]["threshold_grid"]["tau_conflict"] == [0.0, 0.05, 0.1, 0.2]
    boundary = config["access_boundary"]
    assert boundary["api_calls"] == 0
    assert boundary["P1_scm_or_story_access_authorized"] is False
    assert boundary["P1_development_execution_authorized"] is False
    assert boundary["P1_holdout_access_authorized"] is False
    assert boundary["threshold_selection_authorized"] is False


def test_t20_valid_suite_is_balanced_and_all_agreements_pass():
    rows = _jsonl(VALID)
    assert len(rows) == 150
    assert Counter(row["node_count"] for row in rows) == {3: 30, 4: 30, 5: 30, 6: 30, 7: 30}
    assert Counter(row["target_motif"] for row in rows) == {
        "chain": 30, "fork": 30, "collider": 30, "mediator": 30, "diamond": 30
    }
    assert set(Counter(row["preference_regime"] for row in rows).values()) == {25}
    assert all(all(row["agreements"].values()) for row in rows)
    assert all(len(row["selective_decisions"]) == 20 for row in rows)
    assert all(row["P1_scene_or_story_used"] is False for row in rows)
    assert sum(not row["local_argmax_consistent_extension"] for row in rows) == 39


def test_t20_invalid_suite_fails_closed_with_registered_code():
    rows = _jsonl(INVALID)
    assert len(rows) == 30
    assert all(row["expected_error_code"] == row["observed_error_code"] for row in rows)
    assert "invalid_cpdag" in {row["expected_error_code"] for row in rows}
    assert "compelled_edge" in {row["expected_error_code"] for row in rows}
    assert "nonedge" in {row["expected_error_code"] for row in rows}


def test_t20_audit_records_all_gates_and_only_authorizes_t21():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    counts = audit["counts"]
    assert counts["production_reference_forced_agreements"] == 150
    assert counts["invalid_cases_rejected"] == 30
    assert counts["selective_decisions_agreed"] == 3000
    assert counts["selective_accepts"] + counts["selective_abstentions"] == 3000
    assert counts["input_immutability_cases"] == 150
    assert audit["evidence_boundary"]["api_calls"] == 0
    assert audit["evidence_boundary"]["P1_SCMs_or_stories_accessed"] is False
    assert audit["evidence_boundary"]["P1_development_scenes_executed"] == 0
    assert audit["evidence_boundary"]["P1_holdout_accessed"] is False
    assert audit["evidence_boundary"]["threshold_selected"] is False
    assert audit["verdict"]["t20_complete"] is True
    assert audit["verdict"]["h2_forced_conformant"] is True
    assert audit["verdict"]["h2_selective_conformant"] is True
    assert audit["verdict"]["t21_development_only_execution_authorized"] is True
    assert audit["verdict"]["live_model_calls_authorized_at_T20"] is False
    outputs = {item["path"]: item for item in audit["outputs"]}
    for relative in (
        "data/manifests/t20_h2_valid_conformance.jsonl",
        "data/manifests/t20_h2_invalid_conformance.jsonl",
        "reports/t20_h2_conformance.md",
    ):
        path = ROOT / relative
        assert outputs[relative]["bytes"] == path.stat().st_size
        assert outputs[relative]["sha256"] == _sha(path)
