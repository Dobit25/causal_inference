"""Freeze narrow live authorization for the P1V4 look-160 40-scene increment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_look160_incremental_live_materialization_authorization.yaml"
SCRIPT = Path(__file__).resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if cfg["status"] != "explicit_scoped_authorization_requested":
        raise RuntimeError("authorization request status drift")
    checks: dict[str, bool] = {}
    dependencies: list[dict[str, Any]] = []
    paths: dict[str, Path] = {}
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        observed = sha(path) if path.is_file() else None
        checks[f"{name}_hash"] = observed == spec["sha256"]
        dependencies.append({"name": name, "path": spec["path"], "sha256": observed})
        paths[name] = path

    preflight = json.loads(paths["preflight_checkpoint"].read_text(encoding="utf-8"))
    preflight_audit = json.loads(paths["preflight_audit"].read_text(encoding="utf-8"))
    identity_plan = json.loads(paths["incremental_identity_plan"].read_text(encoding="utf-8"))
    auth = cfg["authorization"]
    exact_ids = preflight["dry_run"]["scene_ids"]
    forbidden_keys = (
        "statistical_execution_authorized",
        "semantic_api_authorized",
        "oracle_access_authorized",
        "validation_access_authorized",
        "holdout_access_authorized",
        "downstream_reasoner_authorized",
        "automatic_continuation_authorized",
    )
    target_paths = [
        ROOT / auth["generated_scene_root"],
        ROOT / auth["public_story_root"],
    ]
    checks.update({
        "preflight_ready": preflight["status"] == "PASS_READY_FOR_SEPARATE_LIVE_MATERIALIZATION_AUTHORIZATION",
        "preflight_audit_pass": preflight_audit["status"] == "PASS_OFFLINE_PREFLIGHT" and all(preflight_audit["checks"].values()),
        "explicit_user_authorization_recorded": auth["explicit_user_live_materialization_authorization_recorded"] is True,
        "exact_40_scenes": len(exact_ids) == auth["authorized_scene_count"] == 40,
        "exact_scene_order_matches_identity_plan": exact_ids == identity_plan["incremental_scene_ids_in_execution_order"],
        "exact_120_story_artifacts": preflight["dry_run"]["story_artifact_count"] == auth["authorized_public_story_artifact_count"] == 120,
        "exact_variants": preflight["dry_run"]["story_variants"] == auth["authorized_story_variants"] == ["full", "partial", "ambiguous"],
        "runner_hash_matches_preflight": preflight["runner"]["sha256"] == sha(paths["production_runner"]),
        "targets_still_empty": all(not path.exists() or not any(path.iterdir()) for path in target_paths),
        "no_scope_expansion": not any(auth[key] for key in forbidden_keys),
        "checkpoint_side_effects_zero": all(value in (0, False) for value in cfg["side_effects_at_checkpoint"].values()),
    })
    if not all(checks.values()):
        raise RuntimeError(f"live materialization authorization failed: {[key for key, value in checks.items() if not value]}")

    authorization = {
        "schema_version": "fourgraph.p1_v4_look160_incremental_live_materialization_authorization.v1",
        "task": cfg["task"],
        "status": "PASS_SCOPED_LOOK160_INCREMENTAL_MATERIALIZATION_AUTHORIZATION",
        "authorization": {
            "materialization_authorized": True,
            "exact_scene_ids": exact_ids,
            "scene_count": 40,
            "public_story_artifact_count": 120,
            "story_variants": auth["authorized_story_variants"],
            "generated_scene_root": auth["generated_scene_root"],
            "public_story_root": auth["public_story_root"],
            "duplicate_policy": auth["duplicate_policy"],
            "atomic_write": auth["atomic_write"],
            "concurrency": auth["concurrency"],
            "statistical_execution_authorized": False,
            "semantic_api_authorized": False,
            "oracle_access_authorized": False,
            "validation_access_authorized": False,
            "holdout_access_authorized": False,
            "downstream_reasoner_authorized": False,
            "automatic_continuation_authorized": False,
        },
        "pre_execution_requirements": cfg["pre_execution_requirements"],
        "runner": {"path": paths["production_runner"].relative_to(ROOT).as_posix(), "sha256": sha(paths["production_runner"])},
        "dependencies": dependencies + [
            {"name": "config", "path": CONFIG.relative_to(ROOT).as_posix(), "sha256": sha(CONFIG)},
            {"name": "implementation", "path": SCRIPT.relative_to(ROOT).as_posix(), "sha256": sha(SCRIPT)},
        ],
        "side_effects_at_checkpoint": cfg["side_effects_at_checkpoint"],
        "next_action": "MATERIALIZE_EXACT_40_SCENES_AND_120_PUBLIC_STORIES_ONLY",
    }
    authorization_body = canonical(authorization)
    audit = {
        "schema_version": "fourgraph.p1_v4_look160_incremental_live_materialization_authorization_audit.v1",
        "task": cfg["task"],
        "status": "PASS_SCOPED_AUTHORIZATION",
        "checks": checks,
        "counts": {"authorized_scenes": 40, "authorized_story_artifacts": 120, "materialized_at_checkpoint": 0, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_reads": 0},
        "hashes": {"config": sha(CONFIG), "implementation": sha(SCRIPT), "authorization": hashlib.sha256(authorization_body).hexdigest().upper(), "runner": sha(paths["production_runner"])},
        "next_action": authorization["next_action"],
    }
    report = """# P1V4 look-160 incremental live-materialization authorization

Status: **PASS**. This checkpoint authorizes only the deterministic materialization of the exact 40 frozen incremental scenes and their 120 Full/Partial/Ambiguous public story artifacts, in frozen order and with frozen component seeds.

It does not authorize statistical discovery, semantic API calls, Oracle access, validation, holdout access, downstream reasoning or automatic continuation. No scene or story was materialized while creating this checkpoint.
""".encode("utf-8")
    return {
        ROOT / cfg["outputs"]["authorization"]: authorization_body,
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
    audit_path = ROOT / yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["outputs"]["audit"]
    audit = json.loads(generated[audit_path])
    print(json.dumps({"status": audit["status"], "authorized_scenes": 40, "authorized_stories": 120, "materialized": 0, "api_calls": 0, "check": args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
