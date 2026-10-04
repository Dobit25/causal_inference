"""Frozen look-120 production runner and offline preflight.

This module deliberately separates planning from live execution.  Planning,
hash verification, dry-run and idempotency checks are safe offline operations.
Live materialization/statistical/API adapters are guarded and are not enabled
by this freeze; no invocation of this file can silently broaden the cohort.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/p1_v3_nano_medium_calibration_look120_production_runner.yaml"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest().upper()


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _rel(path: str) -> Path:
    return ROOT / path


def verify_hash_bundle(cfg: dict[str, Any]) -> dict[str, str]:
    bundle: dict[str, str] = {}
    for item in cfg["parents"].values():
        path = _rel(item["path"])
        if not path.is_file():
            raise RuntimeError(f"missing frozen parent: {item['path']}")
        actual = sha256_file(path)
        if actual != str(item["sha256"]).upper():
            raise RuntimeError(f"hash drift for {item['path']}: {actual} != {item['sha256']}")
        bundle[item["path"]] = actual
    for key in ("prompt", "response_schema"):
        path = _rel(cfg["semantic"][key])
        actual = sha256_file(path)
        expected = cfg["semantic"]["prompt_sha256" if key == "prompt" else "schema_sha256"]
        if actual != expected:
            raise RuntimeError(f"semantic contract hash drift: {path}")
        bundle[cfg["semantic"][key]] = actual
    return bundle


def load_identity_rows() -> list[dict[str, Any]]:
    path = _rel("data/manifests/p1_v3_successor_sequential_exact_identities.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [row for row in rows if row.get("role") == "semantic_calibration" and int(row.get("sequence_index", -1)) < 120]
    selected.sort(key=lambda row: int(row["sequence_index"]))
    return selected


def load_exact_plan() -> dict[str, Any]:
    return json.loads((_rel("data/manifests/p1_v3_successor_sequential_exact_identity_plan.json")).read_text(encoding="utf-8"))


def select_cohort(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows = load_identity_rows()
    actual = {row.get("study_id") for row in rows}
    if len(rows) != 120 or len(actual) != 120:
        raise RuntimeError("calibration look is not exactly the frozen 120-scene prefix")
    if any(not row["study_id"].startswith(cfg["cohort"]["registered_prefix"]) for row in rows):
        raise RuntimeError("calibration prefix drift")
    if any(row.get("role") != "semantic_calibration" for row in rows):
        raise RuntimeError("forbidden cohort role selected")
    return rows


def diagnostic_ids(plan: dict[str, Any]) -> tuple[list[str], list[str]]:
    role = plan["roles"]["semantic_calibration"]
    ordered = role["ordered_scene_ids"][:120]
    # The frozen plan uses explicit diagnostic lists.  Never infer them from
    # SCM/oracle data or re-stratify at execution time.
    subsets = plan["diagnostic_subsets"]
    ambiguous = list(subsets["ambiguous_semantic_calibration"])
    nonedge = list(subsets["nonedge_semantic_calibration"])
    if ambiguous != ordered:
        raise RuntimeError("ambiguous diagnostic subset is not the frozen first-look prefix")
    if len(nonedge) != 80 or not set(nonedge).issubset(set(ordered)):
        raise RuntimeError("non-edge diagnostic subset drift")
    return ambiguous, nonedge


def build_statistical_jobs(rows: list[dict[str, Any]], cfg: dict[str, Any], hashes: dict[str, str]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for row in rows:
        for algorithm, repetitions, candidate in (
            ("Single-BOSS", 1, "single_boss"),
            ("Bootstrap-BOSS", int(cfg["statistical_parent"]["bootstrap_boss"]["repetitions_per_scene"]), "bootstrap_boss"),
        ):
            for repetition in range(repetitions):
                identity = {
                    "scene_id": row["study_id"],
                    "contract_scene_id": row["contract_scene_id"],
                    "algorithm": algorithm,
                    "candidate_id": candidate,
                    "repetition": repetition,
                    "seed": row["component_seeds"].get("bootstrap_boss") if algorithm == "Bootstrap-BOSS" else row["master_seed"],
                    "config_hash": sha256_value(hashes),
                }
                identity["run_id"] = sha256_value(identity)
                jobs.append(identity)
    return jobs


def build_semantic_jobs(rows: list[dict[str, Any]], plan: dict[str, Any], cfg: dict[str, Any], hashes: dict[str, str]) -> list[dict[str, Any]]:
    prompt_variants = list(cfg["semantic"]["prompt_variants"])
    by_id = {row["study_id"]: row for row in rows}
    ambiguous, nonedge = diagnostic_ids(plan)
    jobs: list[dict[str, Any]] = []

    def add(scene_id: str, story_variant: str, role: str) -> None:
        row = by_id.get(scene_id)
        if row is None:
            raise RuntimeError(f"diagnostic scene outside look-120 cohort: {scene_id}")
        for prompt_variant in prompt_variants:
            item = {
                "scene_id": scene_id,
                "contract_scene_id": row["contract_scene_id"],
                "story_variant": story_variant,
                "role": role,
                "prompt_variant": prompt_variant,
                "model_snapshot": cfg["semantic"]["model_snapshot"],
                "reasoning_effort": cfg["semantic"]["reasoning_effort"],
                "prompt_sha256": cfg["semantic"]["prompt_sha256"],
                "schema_sha256": cfg["semantic"]["schema_sha256"],
                "graph_input_hash": None,
                "story_hash": None,
                "config_hash": sha256_value(hashes),
            }
            item["logical_id"] = sha256_value(item)
            jobs.append(item)

    for row in rows:
        add(row["study_id"], "full", "certification")
        add(row["study_id"], "partial", "certification")
    for scene_id in ambiguous:
        add(scene_id, "ambiguous", "diagnostic")
    for scene_id in nonedge:
        add(scene_id, "nonedge", "diagnostic")
    return jobs


def build_plan(cfg: dict[str, Any]) -> dict[str, Any]:
    hashes = verify_hash_bundle(cfg)
    rows = select_cohort(cfg)
    exact_plan = load_exact_plan()
    ambiguous, nonedge = diagnostic_ids(exact_plan)
    statistical = build_statistical_jobs(rows, cfg, hashes)
    semantic = build_semantic_jobs(rows, exact_plan, cfg, hashes)
    if len(statistical) != int(cfg["workload"]["statistical_fits"]):
        raise RuntimeError("statistical job count drift")
    if len(semantic) != int(cfg["workload"]["expected_semantic_calls"]):
        raise RuntimeError("semantic job count drift")
    if len({job["run_id"] for job in statistical}) != len(statistical):
        raise RuntimeError("duplicate statistical execution identity")
    if len({job["logical_id"] for job in semantic}) != len(semantic):
        raise RuntimeError("duplicate semantic idempotency identity")
    return {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_look120_execution_plan.v1",
        "status": "FROZEN_OFFLINE_PLAN_ONLY",
        "look": 120,
        "scene_count": len(rows),
        "scene_ids": [row["study_id"] for row in rows],
        "diagnostic_subsets": {"ambiguous": ambiguous, "nonedge": nonedge},
        "planned_statistical_fits": len(statistical),
        "planned_semantic_calls": len(semantic),
        "statistical_jobs": statistical,
        "semantic_jobs": semantic,
        "hash_bundle": hashes,
        "execution_boundary": {
            "scenes_materialized": 0,
            "statistical_fits": 0,
            "semantic_api_calls": 0,
            "oracle_access": False,
            "validation_access": False,
            "holdout_access": False,
        },
        "live_enabled": False,
    }


def idempotency_check(plan: dict[str, Any]) -> dict[str, Any]:
    statistical = plan["statistical_jobs"]
    semantic = plan["semantic_jobs"]
    stat_again = [dict(job) for job in statistical]
    sem_again = [dict(job) for job in semantic]
    return {
        "status": "PASS",
        "statistical_identity_replay": [job["run_id"] for job in stat_again] == [job["run_id"] for job in statistical],
        "semantic_identity_replay": [job["logical_id"] for job in sem_again] == [job["logical_id"] for job in semantic],
        "duplicate_policy": "fail_closed",
    }


def write_outputs(cfg: dict[str, Any], plan: dict[str, Any], idempotency: dict[str, Any]) -> None:
    plan_path = _rel(cfg["execution"]["plan_output"])
    audit_path = _rel(cfg["execution"]["audit_output"])
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_bytes(canonical(plan))
    audit = {
        "schema_version": "fourgraph.p1_v3_nano_medium_calibration_look120_preflight_audit.v1",
        "status": "PASS_OFFLINE_PREFLIGHT_LIVE_BLOCKED",
        "plan_sha256": sha256_file(plan_path),
        "runner_sha256": sha256_file(Path(__file__)),
        "runner_config_sha256": sha256_file(DEFAULT_CONFIG),
        "scene_count": plan["scene_count"],
        "planned_statistical_fits": plan["planned_statistical_fits"],
        "planned_semantic_calls": plan["planned_semantic_calls"],
        "actual_scenes_materialized": 0,
        "actual_statistical_fits": 0,
        "actual_semantic_api_calls": 0,
        "idempotency": idempotency,
        "hash_verification": "PASS",
        "live_execution": "BLOCKED_BY_FROZEN_OFFLINE_RUNNER",
        "missing_live_inputs": [
            cfg["materialization"]["scene_root"],
            cfg["materialization"]["public_story_root"],
        ],
        "oracle_access": False,
        "validation_access": False,
        "holdout_access": False,
        "note": "This checkpoint builds and freezes production plumbing only; no study scenes or provider calls were made.",
    }
    audit_path.write_bytes(canonical(audit))
    print(json.dumps(audit, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--idempotency-test", action="store_true")
    parser.add_argument("--execute", action="store_true", help="refused by this offline freeze")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.execute:
        raise SystemExit("FAIL_CLOSED: live execution is disabled by this runner-freeze config")
    plan = build_plan(cfg)
    idem = idempotency_check(plan)
    if args.idempotency_test and idem["status"] != "PASS":
        raise SystemExit("idempotency test failed")
    write_outputs(cfg, plan, idem)
    if args.dry_run or args.preflight or args.idempotency_test or not args.execute:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
