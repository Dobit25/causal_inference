"""Freeze offline readiness for the P1V4 look-160 incremental materialization."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from materialize_p1_v4_look160_increment import dry_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_look160_incremental_materialization_preflight_authorization_checkpoint.yaml"
SCRIPT = Path(__file__).resolve()
RUNNER = ROOT / "scripts/materialize_p1_v4_look160_increment.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if cfg["status"] != "offline_preflight_only":
        raise RuntimeError("preflight status drift")
    dependencies = []
    checks: dict[str, bool] = {}
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        observed = sha(path) if path.is_file() else None
        checks[f"{name}_hash"] = observed == spec["sha256"]
        dependencies.append({"name": name, "path": spec["path"], "sha256": observed})
    plan = json.loads((ROOT / cfg["parents"]["incremental_plan"]["path"]).read_text(encoding="utf-8"))
    identity_audit = json.loads((ROOT / cfg["parents"]["incremental_identity_audit"]["path"]).read_text(encoding="utf-8"))
    dry = dry_plan()
    checks.update({
        "identity_freeze_pass": identity_audit["status"] == "PASS_OFFLINE_EXACT_IDENTITY_FREEZE",
        "exact_40_scene_scope": dry["scene_count"] == cfg["scope"]["exact_incremental_scenes"] == 40,
        "exact_registered_order": dry["scene_ids"] == plan["incremental_scene_ids_in_execution_order"],
        "exact_three_story_variants": dry["story_variants"] == cfg["scope"]["story_variants"] == ["full", "partial", "ambiguous"],
        "exact_120_story_artifacts": dry["story_artifact_count"] == cfg["scope"]["exact_public_story_artifacts"] == 120,
        "generation_contract_locked": all(dry["generation"][key] == cfg["generation"][key] for key in ("family", "observational_sample_size", "node_count_range", "edge_count_range", "minimum_oracle_cpdag_unresolved_edges")),
        "dry_run_zero_writes": dry["writes_performed"] == 0,
        "dry_run_zero_api": dry["semantic_api_calls"] == 0,
        "diagnostic_membership_not_changed": cfg["diagnostic_boundary"]["incremental_ambiguous_membership"] == 0 and cfg["diagnostic_boundary"]["semantic_call_workload_registered_here"] is False,
        "offline_boundary_zero": all(value in (0, False) for value in cfg["execution_boundary"].values()),
    })
    if not all(checks.values()):
        raise RuntimeError(f"materialization preflight failed: {[key for key, value in checks.items() if not value]}")
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_look160_incremental_materialization_preflight_authorization_checkpoint.v1",
        "task": cfg["task"],
        "status": "PASS_READY_FOR_SEPARATE_LIVE_MATERIALIZATION_AUTHORIZATION",
        "scope": cfg["scope"],
        "generation": cfg["generation"],
        "diagnostic_boundary": cfg["diagnostic_boundary"],
        "dry_run": dry,
        "runner": {"path": RUNNER.relative_to(ROOT).as_posix(), "sha256": sha(RUNNER)},
        "dependencies": dependencies + [
            {"name": "config", "path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha(CONFIG)},
            {"name": "preflight_builder", "path": SCRIPT.relative_to(ROOT).as_posix(), "sha256": sha(SCRIPT)},
        ],
        "authorization": {
            "preflight_pass": True,
            "live_materialization_authorized": False,
            "statistical_execution_authorized": False,
            "semantic_api_authorized": False,
            "oracle_access_authorized": False,
            "validation_or_holdout_authorized": False,
            "automatic_continuation_authorized": False,
        },
        "execution_boundary": cfg["execution_boundary"],
        "next_action": "P1_V4_LOOK160_INCREMENTAL_LIVE_MATERIALIZATION_AUTHORIZATION_CHECKPOINT",
    }
    checkpoint_body = canonical(checkpoint)
    audit = {
        "schema_version": "fourgraph.p1_v4_look160_incremental_materialization_preflight_authorization_checkpoint_audit.v1",
        "task": cfg["task"],
        "status": "PASS_OFFLINE_PREFLIGHT",
        "checks": checks,
        "counts": {"scenes": 40, "story_artifacts": 120, "writes": 0, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_reads": 0},
        "hashes": {"config": sha(CONFIG), "implementation": sha(SCRIPT), "runner": sha(RUNNER), "checkpoint": hashlib.sha256(checkpoint_body).hexdigest().upper()},
        "next_action": checkpoint["next_action"],
    }
    report = """# P1V4 look-160 incremental materialization preflight

Status: **PASS**. The production runner resolves exactly the 40 frozen incremental identities and plans 40 observational scenes plus 120 deterministic Full/Partial/Ambiguous public story artifacts. The dry-run performed zero writes and zero provider calls.

Creating all three public story artifacts preserves the generator contract; it does not add the 40 scenes to the fixed Ambiguous diagnostic subset and does not authorize a future semantic workload. No materialization, statistical discovery, semantic API, Oracle, validation or holdout access has occurred.

A separate scoped live-materialization authorization is required before `--execute` can run.
""".encode("utf-8")
    return {
        ROOT / cfg["outputs"]["checkpoint"]: checkpoint_body,
        ROOT / cfg["outputs"]["audit"]: canonical(audit),
        ROOT / cfg["outputs"]["report"]: report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    for path, content in generated.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != content:
                raise SystemExit(f"non-deterministic artifact drift: {path.relative_to(ROOT)}")
            if not path.exists():
                path.write_bytes(content)
    audit = json.loads(generated[ROOT / yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["outputs"]["audit"]])
    print(json.dumps({"status": audit["status"], "scenes": 40, "story_artifacts": 120, "writes": 0, "api_calls": 0, "check": args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
