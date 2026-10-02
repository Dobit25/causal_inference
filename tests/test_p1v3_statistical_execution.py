from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from adapters.common import graph_record
from adapters.mmpc_adapter import MMPCAdapter, MMPCAdapterError
from adapters.tetrad_adapter import TetradAdapter, TetradAdapterError
from audit_p1v3_statistical_execution import audit_plan
from run_p1v3_statistical_ensemble import build_jobs, load_cfg, pending_jobs, write_plan


CFG = load_cfg(ROOT / "configs/p1v3_statistical_execution.yaml")


def test_plan_has_exact_6150_idempotent_jobs():
    first = build_jobs(CFG)
    second = build_jobs(CFG)
    assert len(first) == 6150
    assert [row["run_id"] for row in first] == [row["run_id"] for row in second]
    assert len({row["run_id"] for row in first}) == 6150
    assert {row["algorithm"] for row in first} == {"BOSS", "Bootstrap-BOSS", "PC", "MMPC", "FGES", "GFCI"}
    assert sum(row["algorithm"] == "Bootstrap-BOSS" for row in first) == 6000
    assert sum(row["algorithm"] == "BOSS" for row in first) == 30


def test_fixture_e2e_all_six_adapters():
    jar = ROOT / CFG["environment"]["tetrad_jar"]
    tetrad = TetradAdapter(jar, CFG["environment"]["tetrad_jar_sha256"], fixture=True)
    mmpc = MMPCAdapter("Rscript", None, CFG["environment"]["bnlearn"], fixture=True)
    from fourgraph.causalds_scd import SceneData
    scene = SceneData("fixture", ("X000", "X001", "X002"), (False, False, False), [[0.0, 1.0, 2.0], [1.0, 2.0, 3.0]])
    params = {
        "penalty_discount": 1.0, "truncation_limit": 3, "alpha": 0.01,
        "depth": -1, "stable_fas": True, "max_degree": -1,
        "symmetric_first_step": False, "faithfulness_assumed": False,
    }
    for algorithm in ("BOSS", "PC", "FGES", "GFCI"):
        graph, _ = tetrad.run(scene, algorithm, params)
        assert graph["nodes"] == ["X000", "X001", "X002"]
    graph, _ = mmpc.run(list(scene.anonymous_names), scene.values, {"alpha": 0.01, "max_sx": None})
    assert graph["graph_type"] == "skeleton"


def test_graph_validator_rejects_malformed_output():
    with pytest.raises(ValueError):
        graph_record(["X000", "X001"], [["X000", "X000"]], [])
    with pytest.raises(ValueError):
        graph_record(["X000", "X001"], [["X000", "X999"]], [])


def test_environment_failure_is_fail_closed():
    jar = ROOT / CFG["environment"]["tetrad_jar"]
    with pytest.raises(TetradAdapterError, match="hash mismatch"):
        TetradAdapter(jar, "0" * 64, fixture=True)
    with pytest.raises(MMPCAdapterError):
        MMPCAdapter("missing-rscript-for-fixture-test", None, "5.3-20260901")


def test_dry_run_plan_and_audit_have_zero_live_work(tmp_path, monkeypatch):
    cfg = copy.deepcopy(CFG)
    cfg["runtime"]["plan_output"] = str(tmp_path / "plan.json")
    cfg["runtime"]["audit_output"] = str(tmp_path / "audit.json")
    cfg["runtime"]["raw_root"] = str(tmp_path / "raw")
    cfg["runtime"]["normalized_root"] = str(tmp_path / "normalized")
    cfg["runtime"]["error_root"] = str(tmp_path / "errors")
    cfg["runtime"]["scene_root"] = str(tmp_path / "scenes")
    plan_path = Path(cfg["runtime"]["plan_output"])
    write_plan(cfg, build_jobs(cfg))
    audit = audit_plan(cfg)
    assert audit["planned_fits"] == 6150
    assert audit["complete_fit_pairs"] == 0
    assert audit["execution_boundary"]["statistical_fits"] == 0
    assert audit["execution_boundary"]["study_scenes_materialized"] == 0
    assert audit["execution_boundary"]["oracle_accessed"] is False
    assert audit["execution_boundary"]["holdout_accessed"] is False
    assert audit["execution_boundary"]["semantic_api_calls"] == 0
    assert plan_path.is_file()


def test_resume_selection_is_idempotent_and_skips_only_complete_pairs(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["runtime"]["raw_root"] = str(tmp_path / "raw")
    cfg["runtime"]["normalized_root"] = str(tmp_path / "normalized")
    jobs = build_jobs(cfg)
    assert len(pending_jobs(cfg, jobs)) == 6150
    (tmp_path / "raw").mkdir()
    (tmp_path / "normalized").mkdir()
    run_id = jobs[0]["run_id"]
    (tmp_path / "raw" / f"{run_id}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "normalized" / f"{run_id}.json").write_text("{}", encoding="utf-8")
    remaining = pending_jobs(cfg, jobs)
    assert len(remaining) == 6149
    assert all(job["run_id"] != run_id for job in remaining)
    assert pending_jobs(cfg, jobs) == remaining
