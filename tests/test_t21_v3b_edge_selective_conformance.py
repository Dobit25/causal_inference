from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_t21_v3b_audit_and_boundaries():
    audit = json.loads((ROOT / "data/manifests/t21_v3b_edge_selective_audit.json").read_text(encoding="utf-8"))
    assert audit["verdict"] == {
        "api_calls": 0,
        "holdout_accessed": False,
        "live_api_calls_authorized": False,
        "offline_conformance_passed": True,
        "partial_graph_contract_ready": True,
        "production_reference_agreement": True,
        "t21_v3b_complete": True,
        "t21_v3c_validation_generation_authorized": True,
        "validation_scenes_generated": False,
    }
    assert audit["counts"]["valid_cases"] == 180
    assert audit["counts"]["decisions"] == 3600
    assert audit["counts"]["invalid_cases_rejected"] == 40
    assert audit["counts"]["off_grid_joint_selection_probes"] == 6
    assert audit["counts"]["source_semantic_selected"] > 0
    assert audit["counts"]["source_closure_propagated"] > 0
    assert audit["counts"]["source_unresolved"] > 0
    assert audit["boundary"]["p1_holdout_scenes_accessed"] == 0


def test_t21_v3b_suite_is_synthetic_and_balanced():
    rows = [json.loads(line) for line in (ROOT / "data/manifests/t21_v3b_edge_selective_valid.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 180
    assert all(row["study_scene_used"] is False for row in rows)
    assert {row["node_count"] for row in rows} == {3, 4, 5, 6, 7}
    regimes = {}
    for row in rows:
        regimes[row["preference_regime"]] = regimes.get(row["preference_regime"], 0) + 1
        assert len(row["threshold_decisions"]) == 20
        assert all(decision["method"] == "H2_EDGE_SELECTIVE" for decision in row["threshold_decisions"])
    assert set(regimes.values()) == {30}
    probes = [row["off_grid_joint_selection_probe"] for row in rows if "off_grid_joint_selection_probe" in row]
    assert len(probes) == 6
    assert all(len(probe["decision"]["candidate_directions"]) == 3 for probe in probes)
    assert all(len(probe["decision"]["selected_directions"]) == 2 for probe in probes)


def test_t21_v3b_replay_is_byte_exact():
    result = subprocess.run(
        [sys.executable, "scripts/build_t21_v3b_edge_selective_conformance.py", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
