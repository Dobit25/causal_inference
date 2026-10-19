"""Create a non-executing, fail-closed authorization checkpoint for calibration look 120."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_live_materialization_authorization.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    dependencies = []
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        observed = sha(path) if path.is_file() else None
        checks[f"{name}_hash"] = observed == spec["sha256"]
        dependencies.append({"name": name, "path": spec["path"], "sha256": observed})

    preflight = json.loads((ROOT / cfg["parents"]["materialization_preflight"]["path"]).read_text(encoding="utf-8"))
    preflight_audit = json.loads((ROOT / cfg["parents"]["materialization_preflight_audit"]["path"]).read_text(encoding="utf-8"))
    exact_plan = json.loads((ROOT / cfg["parents"]["exact_identity_plan"]["path"]).read_text(encoding="utf-8"))
    scene_ids = preflight["exact_scene_ids_in_execution_order"]
    scope = cfg["scope"]
    expected = exact_plan["exact_scene_ids_in_execution_order"][: int(scope["registered_look"])]
    required_false = (
        "scene_materialization_authorized",
        "story_generation_authorized",
        "statistical_execution_authorized",
        "semantic_api_calls_authorized",
        "oracle_access_authorized",
        "holdout_access_authorized",
    )
    checks.update(
        {
            "preflight_pass": preflight["status"] == "PASS_FROZEN_OFFLINE_PREFLIGHT" and preflight_audit["status"] == "PASS",
            "exact_120_scene_ids": len(scene_ids) == int(scope["exact_scene_count"]),
            "prefix_identity_match": scene_ids == expected,
            "namespace_only": all(scene_id.startswith(scope["scene_namespace"]) for scene_id in scene_ids),
            "preflight_boundary_zero": all(value in (0, False) for value in preflight["execution_boundary"].values()),
            "reserved_scene_root_absent": not (ROOT / scope["scene_root"]).exists(),
            "reserved_story_root_absent": not (ROOT / scope["public_story_root"]).exists(),
            "live_permissions_not_implicitly_granted": all(cfg["authorization"][key] is False for key in required_false),
            "no_explicit_user_authorization_claimed": cfg["authorization"]["explicit_user_live_materialization_authorization_recorded"] is False,
        }
    )
    passed = all(checks.values())
    checkpoint = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_live_materialization_authorization_checkpoint.v1",
        "task": cfg["task"],
        "status": "PASS_READY_FOR_EXPLICIT_LIVE_MATERIALIZATION_AUTHORIZATION" if passed else "FAIL",
        "scope": {**scope, "exact_scene_ids_in_execution_order": scene_ids},
        "parents": dependencies,
        "authorization": cfg["authorization"],
        "guards": cfg["guards"],
        "execution_boundary": {"scenes_materialized": 0, "observations_generated": 0, "stories_generated": 0, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_access": False, "holdout_access": False},
        "next_action": "EXPLICIT_USER_LIVE_MATERIALIZATION_AUTHORIZATION_REQUIRED" if passed else "AUTHORIZATION_CHECKPOINT_REMEDIATION_ONLY",
    }
    checkpoint_bytes = canonical(checkpoint)
    audit = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_live_materialization_authorization_audit.v1",
        "task": cfg["task"],
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "counts": {"authorized_scene_scope": len(scene_ids), "materialized_scenes": 0, "statistical_fits": 0, "semantic_api_calls": 0},
        "hashes": {"config": sha(CONFIG), "checkpoint": hashlib.sha256(checkpoint_bytes).hexdigest().upper()},
        "execution_boundary": checkpoint["execution_boundary"],
        "next_action": checkpoint["next_action"],
    }
    report = f"""# P1V4 calibration look-120 live-materialization authorization checkpoint

Status: **{audit['status']}**. The checkpoint binds exactly **{len(scene_ids)}** frozen `P1V4SC` identities, the canonical `cau` environment, generator/materializer provenance, and empty reserved output paths.

It does **not** itself claim or grant live execution: `explicit_user_live_materialization_authorization_recorded=false`. No scene, observation, story, fit, API request, Oracle read, or holdout access occurred. A subsequent explicit authorization may permit only the materialization and registered public-story creation in this exact scope; statistical discovery and semantic API calls remain separately locked.
""".encode("utf-8")
    return {
        ROOT / cfg["outputs"]["checkpoint"]: checkpoint_bytes,
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
    audit_path = ROOT / "data/manifests/p1_v4_independent_calibration_look120_live_materialization_authorization_audit.json"
    audit = json.loads(generated[audit_path])
    print(json.dumps({"status": audit["status"], "authorized_scene_scope": 120, "materialized_scenes": 0, "api_calls": 0, "check": args.check}))
    if audit["status"] != "PASS":
        raise SystemExit("authorization checkpoint failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
