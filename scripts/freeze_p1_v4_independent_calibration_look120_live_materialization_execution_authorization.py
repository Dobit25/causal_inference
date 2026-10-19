"""Freeze the user's explicit, narrow authorization for look-120 materialization."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_live_materialization_execution_authorization.yaml"

def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def build() -> dict[Path, bytes]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks, deps = {}, []
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]; observed = sha(path) if path.is_file() else None
        checks[f"{name}_hash"] = observed == spec["sha256"]
        deps.append({"name": name, "path": spec["path"], "sha256": observed})
    checkpoint = json.loads((ROOT / cfg["parents"]["authorization_checkpoint"]["path"]).read_text())
    preflight = json.loads((ROOT / cfg["parents"]["materialization_preflight"]["path"]).read_text())
    auth = cfg["authorization"]
    checks.update({
        "authorization_checkpoint_ready": checkpoint["status"] == "PASS_READY_FOR_EXPLICIT_LIVE_MATERIALIZATION_AUTHORIZATION",
        "preflight_pass": preflight["status"] == "PASS_FROZEN_OFFLINE_PREFLIGHT",
        "explicit_user_authorization": auth["explicit_user_live_materialization_authorization_recorded"] is True,
        "exact_scope": auth["materialize_exact_scenes"] == 120 and auth["generate_exact_public_stories"] == 360,
        "variants_exact": auth["allowed_story_variants"] == ["full", "partial", "ambiguous"],
        "no_additional_scientific_execution": not any(auth[key] for key in ("statistical_execution_authorized", "semantic_api_calls_authorized", "oracle_access_authorized", "holdout_access_authorized", "downstream_reasoner_authorized", "automatic_continuation_authorized")),
    })
    passed = all(checks.values())
    artifact = {
        "schema_version": "fourgraph.p1_v4_independent_calibration_look120_live_materialization_execution_authorization.v1",
        "task": cfg["task"], "status": "PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION" if passed else "FAIL",
        "authorization": auth, "dependencies": deps,
        "scope": {"scene_ids": preflight["exact_scene_ids_in_execution_order"], "scene_root": preflight["reserved_outputs"]["scene_root"], "public_story_root": preflight["reserved_outputs"]["public_story_root"]},
        "next_action": "MATERIALIZE_120_SCENES_AND_360_PUBLIC_STORIES_ONLY" if passed else "AUTHORIZATION_REMEDIATION_ONLY",
    }
    artifact_bytes = canonical(artifact)
    audit = {"schema_version": "fourgraph.p1_v4_independent_calibration_look120_live_materialization_execution_authorization_audit.v1", "task": cfg["task"], "status": "PASS" if passed else "FAIL", "checks": checks, "hashes": {"config": sha(CONFIG), "authorization": hashlib.sha256(artifact_bytes).hexdigest().upper()}, "side_effects_before_authorization": {"scenes_materialized": 0, "stories_generated": 0, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_access": False, "holdout_access": False}, "next_action": artifact["next_action"]}
    report = f"# P1V4 calibration look-120 live materialization authorization\n\nStatus: **{audit['status']}**. The user authorization permits only 120 deterministic scene materializations and 360 registered public stories (Full, Partial, Ambiguous). Statistical discovery, semantic API, Oracle, holdout, reasoner and automatic continuation remain forbidden.\n".encode()
    return {ROOT / cfg["outputs"]["authorization"]: artifact_bytes, ROOT / cfg["outputs"]["audit"]: canonical(audit), ROOT / cfg["outputs"]["report"]: report}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true"); args = parser.parse_args()
    generated = build()
    if args.check:
        for path, content in generated.items():
            if not path.is_file() or path.read_bytes() != content: raise SystemExit(f"artifact drift: {path.relative_to(ROOT)}")
    else:
        for path, content in generated.items(): path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    audit = json.loads(generated[ROOT / yaml.safe_load(CONFIG.read_text())["outputs"]["audit"]])
    print(json.dumps({"status": audit["status"], "scenes": 120, "stories": 360, "api_calls": 0, "check": args.check}))
    if audit["status"] != "PASS": raise SystemExit("authorization freeze failed")
    return 0

if __name__ == "__main__": raise SystemExit(main())
