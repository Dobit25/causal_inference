from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.common import canonical_json, sha256_file
from adapters.mmpc_adapter import MMPCAdapter
from adapters.tetrad_adapter import TetradAdapter
from fourgraph.bootstrap_boss import iter_bootstrap_indices, standardize_bootstrap_sample
from fourgraph.causalds_scd import SceneData
from fourgraph.p1_generation import standardize
from materialize_p1v3_development import load_identities, materialize

CONFIG = ROOT / "configs/p1v3_statistical_execution.yaml"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def load_cfg(path: Path = CONFIG) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _execution_hash_bundle(cfg: dict[str, Any]) -> dict[str, str]:
    paths = [cfg["protocol_manifest"], cfg["algorithm_manifest"], cfg["identity_manifest"], cfg["materialization_generator"], "configs/p1v3_statistical_execution.yaml"]
    return {path: sha256_file(ROOT / path) for path in paths}


def _seed(scene_id: str, algorithm: str, candidate_id: str, repetition: int, config_hash: str) -> int:
    material = f"P1V3|{config_hash}|{scene_id}|{algorithm}|{candidate_id}|{repetition}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big", signed=False)


def build_jobs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    all_identities = _jsonl(ROOT / cfg["identity_manifest"])
    identities = sorted((row for row in all_identities if row.get("role") == "method_development"), key=lambda row: row["study_id"])
    if len(identities) != 30 or {row["study_id"] for row in identities} != {f"P1V3SD{i:03d}" for i in range(30)}:
        raise RuntimeError("identity manifest is not exactly the frozen 30-scene development cohort")
    hashes = _execution_hash_bundle(cfg)
    protocol = yaml.safe_load((ROOT / cfg["protocol_manifest"]).read_text(encoding="utf-8"))
    algorithm_manifest = yaml.safe_load((ROOT / cfg["algorithm_manifest"]).read_text(encoding="utf-8"))
    config_hash = sha256_bytes(canonical_json(hashes))
    jobs: list[dict[str, Any]] = []
    if protocol["statistical_conditions"]["bootstrap_candidates"] != [f"C{i}" for i in range(1, 7)]:
        raise RuntimeError("bootstrap candidate manifest drift")
    methods = [
        ("BOSS", "baseline", int(algorithm_manifest["methods"]["single_boss"].get("repetitions", 1))),
        ("PC", "primary", int(algorithm_manifest["methods"]["pc"].get("repetitions", 1))),
        ("MMPC", "primary", int(algorithm_manifest["methods"]["mmpc"].get("repetitions", 1))),
        ("FGES", "primary", int(algorithm_manifest["methods"]["fges"].get("repetitions", 1))),
        ("GFCI", "sensitivity", int(algorithm_manifest["methods"]["gfci"].get("repetitions", 1))),
        ("Bootstrap-BOSS", "bootstrap_base", int(algorithm_manifest["methods"]["bootstrap_boss"]["repetitions"])),
    ]
    for identity in identities:
        for algorithm, candidate, repetitions in methods:
            for repetition in range(repetitions):
                job = {"scene_id": identity["study_id"], "contract_scene_id": identity["contract_scene_id"], "algorithm": algorithm, "candidate_id": candidate, "repetition": repetition, "seed": _seed(identity["study_id"], algorithm, candidate, repetition, config_hash), "config_hash": config_hash, "dependency_hashes": hashes}
                job["run_id"] = sha256_bytes(canonical_json(job))
                jobs.append(job)
    if len(jobs) != 6150 or len({job["run_id"] for job in jobs}) != 6150:
        raise RuntimeError("planned fit count or execution identity is not unique")
    return jobs


def load_method_parameters(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    manifest = yaml.safe_load((ROOT / cfg["algorithm_manifest"]).read_text(encoding="utf-8"))["methods"]
    return {
        "BOSS": {"penalty_discount": manifest["single_boss"]["penalty_discount"], "truncation_limit": manifest["single_boss"]["truncation_limit"]},
        "PC": {"alpha": manifest["pc"]["alpha"], "depth": manifest["pc"]["depth"], "stable_fas": manifest["pc"]["stable_fas"]},
        "MMPC": {"alpha": manifest["mmpc"]["alpha"], "max_sx": manifest["mmpc"]["max_sx"]},
        "FGES": {"penalty_discount": manifest["fges"]["penalty_discount"], "max_degree": manifest["fges"]["max_degree"], "symmetric_first_step": manifest["fges"]["symmetric_first_step"], "faithfulness_assumed": manifest["fges"]["faithfulness_assumed"]},
        "GFCI": {"penalty_discount": manifest["gfci"]["penalty_discount"], "alpha": manifest["gfci"]["alpha"], "depth": manifest["gfci"]["depth"], "max_degree": manifest["gfci"]["max_degree"], "faithfulness_assumed": manifest["gfci"]["faithfulness_assumed"]},
    }


def write_plan(cfg: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    plan = {"schema_version": "fourgraph.p1v3_statistical_execution_plan.v1", "task": cfg["task"], "status": "DRY_RUN_PLAN_ONLY", "planned_jobs": len(jobs), "jobs_by_algorithm": {name: sum(job["algorithm"] == name for job in jobs) for name in ("BOSS", "Bootstrap-BOSS", "PC", "MMPC", "FGES", "GFCI")}, "concurrency": cfg["runtime"]["concurrency"], "retry_count": cfg["runtime"]["retry_count"], "dependency_hashes": jobs[0]["dependency_hashes"], "execution_boundary": {"study_scenes_materialized": 0, "statistical_fits": 0, "oracle_accessed": False, "holdout_accessed": False, "semantic_api_calls": 0}, "jobs": jobs}
    path = ROOT / cfg["runtime"]["plan_output"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(plan))
    return plan


def pending_jobs(cfg: dict[str, Any], jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only jobs lacking a complete raw+normalized artifact pair."""
    raw_root = ROOT / cfg["runtime"]["raw_root"]
    normalized_root = ROOT / cfg["runtime"]["normalized_root"]
    return [
        job for job in jobs
        if not ((raw_root / f"{job['run_id']}.json").is_file()
                and (normalized_root / f"{job['run_id']}.json").is_file())
    ]


def _assert_environment(cfg: dict[str, Any]) -> None:
    audit_path = ROOT / "data/manifests/p1v3_statistical_ensemble_phase_c_verification_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("status") != "PASS_EXECUTION_READY" or not audit.get("phase_d_authorized"):
        raise RuntimeError("Phase C execution-readiness audit is not PASS")
    if cfg["runtime"]["oracle_access"] or cfg["runtime"]["holdout_access"]:
        raise RuntimeError("Oracle/holdout access is forbidden")


def execute(cfg: dict[str, Any], jobs: list[dict[str, Any]]) -> None:
    if not cfg["authorization"]["execute"]:
        raise RuntimeError("live Phase D execution is not authorized in this readiness config")
    _assert_environment(cfg)
    if int(cfg["runtime"]["concurrency"]) != 1:
        raise RuntimeError("initial production execution is fail-closed to conservative concurrency=1")
    generator_cfg = yaml.safe_load((ROOT / cfg["materialization_generator"]).read_text(encoding="utf-8"))["generator"]
    identities = load_identities(ROOT / cfg["identity_manifest"])
    scene_root = ROOT / cfg["runtime"]["scene_root"]
    scene_records = materialize(identities, generator_cfg, scene_root)
    (scene_root / "manifest.json").write_bytes(canonical_json({"schema_version": "fourgraph.p1v3_materialized_scene_manifest.v1", "records": scene_records}))
    tetrad = TetradAdapter(ROOT / cfg["environment"]["tetrad_jar"], cfg["environment"]["tetrad_jar_sha256"])
    mmpc = MMPCAdapter(cfg["environment"]["rscript"], Path(cfg["environment"]["r_library"]), cfg["environment"]["bnlearn"])
    raw_root = ROOT / cfg["runtime"]["raw_root"]; normalized_root = ROOT / cfg["runtime"]["normalized_root"]; error_root = ROOT / cfg["runtime"]["error_root"]
    raw_root.mkdir(parents=True, exist_ok=True); normalized_root.mkdir(parents=True, exist_ok=True); error_root.mkdir(parents=True, exist_ok=True)
    identity_by_scene = {row["study_id"]: row for row in identities}
    method_parameters = load_method_parameters(cfg)
    for job in pending_jobs(cfg, jobs):
        raw_path = raw_root / f"{job['run_id']}.json"; normalized_path = normalized_root / f"{job['run_id']}.json"; error_path = error_root / f"{job['run_id']}.json"
        identity = identity_by_scene[job["scene_id"]]
        scene_dir = scene_root / job["scene_id"]
        values = np.load(scene_dir / "observations.npy", allow_pickle=False)
        metadata = json.loads((scene_dir / "metadata.json").read_text(encoding="utf-8"))
        if metadata["observation_sha256"] != sha256_file(scene_dir / "observations.npy"):
            raise RuntimeError(f"scene input hash drift: {job['scene_id']}")
        nodes = metadata["nodes"]
        scene_data = SceneData(job["contract_scene_id"], tuple(nodes), tuple(False for _ in nodes), standardize(values))
        started = time.perf_counter()
        try:
            if job["algorithm"] == "Bootstrap-BOSS":
                bootstrap_spec = yaml.safe_load((ROOT / cfg["algorithm_manifest"]).read_text(encoding="utf-8"))["methods"]["bootstrap_boss"]
                _, indices = next(item for item in iter_bootstrap_indices(job["contract_scene_id"], row_count=int(bootstrap_spec["sample_size"]), sample_size=int(bootstrap_spec["sample_size"]), repetitions=int(bootstrap_spec["repetitions"])) if item[0] == job["repetition"])
                fit_data = SceneData(job["contract_scene_id"], tuple(nodes), tuple(False for _ in nodes), standardize_bootstrap_sample(values, indices))
                graph, adapter_seconds = tetrad.run(fit_data, "BOSS", method_parameters["BOSS"])
            elif job["algorithm"] == "MMPC":
                graph, adapter_seconds = mmpc.run(nodes, values, method_parameters["MMPC"])
            else:
                graph, adapter_seconds = tetrad.run(scene_data, job["algorithm"], method_parameters[job["algorithm"]])
            raw = {"schema_version": "fourgraph.p1v3_raw_statistical_fit.v1", "run_id": job["run_id"], "job": job, "adapter_seconds": adapter_seconds, "graph": graph}
            raw_bytes = canonical_json(raw); raw_path.write_bytes(raw_bytes)
            normalized = {"schema_version": "fourgraph.p1v3_normalized_statistical_fit.v1", "run_id": job["run_id"], "scene_id": job["scene_id"], "algorithm": job["algorithm"], "candidate_id": job["candidate_id"], "seed": job["seed"], "input_sha256": metadata["observation_sha256"], "raw_output_sha256": sha256_bytes(raw_bytes), "runtime_seconds": time.perf_counter() - started, "graph": graph}
            normalized_path.write_bytes(canonical_json(normalized))
        except Exception as exc:
            error_path.write_bytes(canonical_json({"schema_version": "fourgraph.p1v3_fit_error.v1", "run_id": job["run_id"], "error_type": type(exc).__name__, "error": str(exc), "runtime_seconds": time.perf_counter() - started}))
            raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    cfg = load_cfg(args.config)
    jobs = build_jobs(cfg)
    plan = write_plan(cfg, jobs)
    if args.execute or args.resume:
        execute(cfg, jobs)
    if args.audit:
        from audit_p1v3_statistical_execution import audit_plan
        print(json.dumps(audit_plan(cfg), ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "PASS_DRY_RUN", "planned_fits": len(jobs), "actual_fits": 0, "study_scenes_materialized": 0, "oracle_accessed": False, "holdout_accessed": False, "plan_sha256": sha256_file(ROOT / cfg["runtime"]["plan_output"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
