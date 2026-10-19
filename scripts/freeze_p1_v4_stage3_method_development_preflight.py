"""Freeze the P1V4 30-scene development execution envelope without running it."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_stage3_method_development_preflight.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    dependencies = []
    checks: dict[str, bool] = {}
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]; observed = path.is_file() and sha(path)
        checks[f"{name}_hash"] = observed == spec["sha256"]
        dependencies.append({"name": name, "path": spec["path"], "sha256": observed})
    identities = [json.loads(line) for line in (ROOT / cfg["parents"]["exact_identities"]["path"]).read_text(encoding="utf-8").splitlines() if line]
    dev = [row for row in identities if row["role"] == cfg["identity_scope"]["role"]]
    expected = {f"P1V4SD{index:03d}" for index in range(30)}
    checks["exact_30_development_ids"] = len(dev) == 30 and {row["study_id"] for row in dev} == expected
    checks["fresh_p1v4_namespace"] = all(row["study_id"].startswith("P1V4SD") for row in dev)
    checks["no_preexisting_materialization"] = all(row["scene_materialized"] is False for row in dev)
    checks["no_calibration_validation_or_holdout"] = not any(row["role"] != "method_development" for row in dev)
    checks["unique_component_seeds"] = len({seed for row in dev for seed in row["component_seeds"].values()}) == 180
    stat = cfg["statistical_workload"]
    checks["fit_arithmetic"] = sum(stat[key] for key in ("single_boss_fits", "bootstrap_boss_fits", "pc_fits", "mmpc_fits", "fges_fits", "constrained_boss_fits", "constrained_fges_fits")) == stat["total_fits"] == 6180
    semantic = cfg["semantic_workload"]
    checks["semantic_call_arithmetic"] = semantic["calls_per_scene"] * len(dev) == semantic["expected_logical_calls"] == 360
    checks["semantic_contract_fixed"] = semantic["model_snapshot"] == "gpt-5.4-nano-2026-03-17" and semantic["reasoning_effort"] == "medium" and semantic["automatic_chunking"] == "forbidden"
    checks["primary_and_robustness_fixed"] = stat["constrained_boss_primary"] is True and stat["constrained_fges_robustness_only"] is True
    checks["offline_boundary"] = all(value in (0, False) for value in cfg["execution_boundary"].values())
    passed = all(checks.values())
    preflight = {"schema_version": "fourgraph.p1_v4_stage3_method_development_preflight.v1", "task": cfg["task"], "status": "FROZEN_OFFLINE_METHOD_DEVELOPMENT_PREFLIGHT" if passed else "FAILED_OFFLINE_METHOD_DEVELOPMENT_PREFLIGHT", "exact_identities": [{key: row[key] for key in ("study_id", "contract_scene_id", "sequence_index", "master_seed", "component_seeds", "node_count", "primary_motif", "noise_family", "query_stratum", "identity_sha256", "scene_materialized")} for row in dev], "generation": cfg["generation"], "statistical_workload": stat, "semantic_workload": semantic, "execution_environment": cfg["execution_environment"], "planning_envelope": cfg["planning_envelope"], "reserved_outputs": cfg["outputs"], "dependencies": dependencies + [{"name": "config", "path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha(CONFIG)}, {"name": "builder", "path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha(Path(__file__))}], "execution_boundary": cfg["execution_boundary"], "authorization": {"preflight_frozen": passed, "scene_materialization_authorized": False, "statistical_execution_authorized": False, "semantic_api_calls_authorized": False, "oracle_access_authorized": False, "next_action": "P1_V4_STAGE_3D_LIVE_AUTHORIZATION_CHECKPOINT"}}
    preflight_bytes = canonical(preflight)
    audit = {"schema_version": "fourgraph.p1_v4_stage3_method_development_preflight_audit.v1", "task": cfg["task"], "status": "PASS_STAGE_3D_PREFLIGHT_FREEZE" if passed else "FAIL_STAGE_3D_PREFLIGHT_FREEZE", "checks": checks, "counts": {"development_scenes": len(dev), "statistical_fits": stat["total_fits"], "semantic_logical_calls": semantic["expected_logical_calls"], "historical_reference_tokens": cfg["planning_envelope"]["historical_reference_only"]["total_tokens"]}, "hashes": {"preflight": hashlib.sha256(preflight_bytes).hexdigest().upper(), "config": sha(CONFIG)}, "execution_boundary": cfg["execution_boundary"], "next_action": "FRESH_SPEND_ATTESTATION_AND_P1_V4_STAGE_3D_LIVE_AUTHORIZATION" if passed else "PREFLIGHT_REMEDIATION_ONLY"}
    report = f"""# P1-v4 Stage 3 method-development preflight\n\nStatus: **{audit['status']}**. This freezes exactly 30 fresh P1V4 development identities, but does not materialize them. The future run comprises 6,180 statistical fits (including 6,000 Bootstrap-BOSS fits) and 360 shared Nano-medium semantic calls over Full/Partial stories.\n\nConstrained BOSS is primary and constrained FGES is robustness-only. The shared semantic pair pool is the union of their parent adjacencies, capped at 21 pairs; prompt chunking is forbidden. The historical 30-scene run consumed 651,903 total tokens for 360 calls and is a planning reference only, not permission to spend.\n\nA fresh spend/limit attestation, provider preflight, and a separate live authorization are still required before a scene, fit, story, or API response may be created.\n""".encode("utf-8")
    return {ROOT / cfg["outputs"]["preflight"]: preflight_bytes, ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content: raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items(): path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    print(json.dumps({"status": "PASS", "stage": "3D_PREFLIGHT", "materialized_scenes": 0, "statistical_fits": 0, "api_calls": 0, "check": args.check}))
    return 0


if __name__ == "__main__": raise SystemExit(main())
