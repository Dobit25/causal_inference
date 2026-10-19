"""Freeze a non-writing materialization preflight for P1V4 calibration look 120."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from materialize_p1_v4_independent_calibration import materialization_dry_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_materialization_preflight.yaml"
MATERIALIZER = ROOT / "scripts/p1_v4_independent_calibration.py"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    dependencies = []
    checks: dict[str, bool] = {}
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        observed = sha(path) if path.is_file() else None
        checks[f"{name}_hash"] = observed == spec["sha256"]
        dependencies.append({"name": name, "path": spec["path"], "sha256": observed})

    identity_rows = rows(ROOT / cfg["parents"]["exact_identities"]["path"])
    plan = json.loads((ROOT / cfg["parents"]["exact_identity_plan"]["path"]).read_text(encoding="utf-8"))
    look = int(cfg["selection"]["registered_look"])
    ordered_ids = plan["exact_scene_ids_in_execution_order"][:look]
    by_id = {row["study_id"]: row for row in identity_rows}
    selected = [by_id[study_id] for study_id in ordered_ids]
    ambiguous = [row for row in selected if "ambiguous_semantic_calibration" in row["diagnostic_memberships"]]
    nonedge = [row for row in selected if "nonedge_semantic_calibration" in row["diagnostic_memberships"]]
    checks.update(
        {
            "exact_look_120_count": len(selected) == cfg["selection"]["exact_scene_count"] == look,
            "exact_prefix_matches_plan": ordered_ids == plan["exact_scene_ids_in_execution_order"][:look],
            "calibration_role_only": all(row["role"] == cfg["selection"]["allowed_role"] for row in selected),
            "namespace_only": all(row["study_id"].startswith(cfg["selection"]["calibration_namespace"]) for row in selected),
            "unique_scene_ids": len(set(ordered_ids)) == len(ordered_ids),
            "unmaterialized_identities": all(row["scene_materialized"] is False for row in selected),
            "ambiguous_subset_exact": len(ambiguous) == cfg["selection"]["ambiguous_subset_count"],
            "nonedge_subset_exact": len(nonedge) == cfg["selection"]["nonedge_subset_count"],
            "nonedge_nested": {row["study_id"] for row in nonedge} <= {row["study_id"] for row in ambiguous},
            "no_reserved_scene_output": not (ROOT / cfg["reserved_outputs"]["scene_root"]).exists(),
            "no_reserved_story_output": not (ROOT / cfg["reserved_outputs"]["public_story_root"]).exists(),
            "no_future_manifest": not (ROOT / cfg["reserved_outputs"]["materialization_manifest"]).exists() and not (ROOT / cfg["reserved_outputs"]["public_input_manifest"]).exists(),
            "offline_boundary": all(value in (0, False) for value in cfg["execution_boundary"].values()),
        }
    )
    dry = materialization_dry_plan()
    checks["materializer_dry_plan_matches"] = dry["scene_ids"] == ordered_ids and dry["scene_count"] == look and dry["writes_performed"] == 0
    checks["no_blueprint_generation_in_preflight"] = dry["writes_performed"] == 0
    passed = all(checks.values())
    preflight = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_materialization_preflight.v1",
        "task": cfg["task"],
        "status": "PASS_FROZEN_OFFLINE_PREFLIGHT" if passed else "FAIL_FROZEN_OFFLINE_PREFLIGHT",
        "exact_scene_ids_in_execution_order": ordered_ids,
        "identity_sha256": sha(ROOT / cfg["parents"]["exact_identities"]["path"]),
        "selection": cfg["selection"],
        "generation": cfg["generation"],
        "reserved_outputs": cfg["reserved_outputs"],
        "materializer": {
            "path": "scripts/materialize_p1_v4_independent_calibration.py",
            "sha256": sha(ROOT / "scripts/materialize_p1_v4_independent_calibration.py"),
            "default_mode": "dry_run_only",
        },
        "dry_plan": dry,
        "dependencies": dependencies + [
            {"name": "config", "path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha(CONFIG)},
            {"name": "preflight_builder", "path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": sha(Path(__file__))},
        ],
        "execution_boundary": cfg["execution_boundary"],
        "authorization": {
            "preflight_frozen": passed,
            "scene_materialization_authorized": False,
            "story_generation_authorized": False,
            "statistical_execution_authorized": False,
            "semantic_api_calls_authorized": False,
            "oracle_access_authorized": False,
            "holdout_access_authorized": False,
            "next_action": "P1_V4_INDEPENDENT_CALIBRATION_LOOK120_LIVE_MATERIALIZATION_AUTHORIZATION_CHECKPOINT",
        },
    }
    preflight_bytes = canonical(preflight)
    audit = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_materialization_preflight_audit.v1",
        "task": cfg["task"],
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "counts": {
            "exact_look_scenes": len(selected),
            "ambiguous_diagnostic_scenes": len(ambiguous),
            "nonedge_diagnostic_scenes": len(nonedge),
            "materialized_scenes": 0,
            "statistical_fits": 0,
            "semantic_api_calls": 0,
        },
        "hashes": {
            "config": sha(CONFIG),
            "preflight": hashlib.sha256(preflight_bytes).hexdigest().upper(),
            "materializer": preflight["materializer"]["sha256"],
        },
        "execution_boundary": cfg["execution_boundary"],
        "next_action": preflight["authorization"]["next_action"] if passed else "PREFLIGHT_REMEDIATION_ONLY",
    }
    report = f"""# P1V4 calibration look-120 generator/materialization preflight

Status: **{audit['status']}**. This preflight selects exactly **{len(selected)}** already-frozen `P1V4SC` identities in registered execution order. It hash-pins the linear non-Gaussian generator, source materialization logic, deterministic T19 story protocol, and the new default-dry-run calibration materializer.

It created no blueprint, SCM, observation, public story, statistical fit, semantic response, Oracle read, or holdout access. The first look contains **{len(ambiguous)}** Ambiguous diagnostic scenes and a nested **{len(nonedge)}** non-edge diagnostic subset. A separate live-materialization authorization remains mandatory.
""".encode("utf-8")
    return {
        ROOT / cfg["outputs"]["preflight"]: preflight_bytes,
        ROOT / cfg["outputs"]["audit"]: canonical(audit),
        ROOT / cfg["outputs"]["report"]: report,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content:
                raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    audit_path = ROOT / "data/manifests/p1_v4_independent_calibration_look120_materialization_preflight_audit.json"
    audit = json.loads(generated[audit_path])
    print(json.dumps({"status": audit["status"], "look": 120, "materialized_scenes": 0, "api_calls": 0, "check": args.check}))
    if audit["status"] != "PASS":
        raise SystemExit("offline preflight failed; remediation only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
