"""Preflight and separately freeze scoped live materialization authorization."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from materialize_p1_v4_partial_high_supplemental80 import dry_plan

CONFIG = ROOT / "configs/p1_v4_partial_high_supplemental80_materialization_preflight.yaml"
RUNNER = ROOT / "scripts/materialize_p1_v4_partial_high_supplemental80.py"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def outputs(cfg: dict[str, Any], keys: tuple[str, ...], bodies: tuple[bytes, ...], check: bool) -> None:
    for key, body in zip(keys, bodies, strict=True):
        path = ROOT / cfg["outputs"][key]
        if check:
            require(path.is_file() and path.read_bytes() == body, f"byte replay drift: {key}")
        else:
            require(not path.exists() or path.read_bytes() == body, f"existing artifact drift: {key}")
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)


def preflight(check: bool) -> dict[str, Any]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    require(cfg["status"] == "offline_preflight_before_scoped_materialization", "preflight status drift")
    hashes = {}
    for name, spec in cfg["parents"].items():
        p = ROOT / spec["path"]
        require(p.is_file() and digest(p) == spec["sha256"], f"parent hash drift: {name}")
        hashes[name] = {"path": spec["path"], "sha256": spec["sha256"]}
    dry = dry_plan()
    require(dry["status"] == "DRY_RUN_PASS" and dry["scene_count"] == 80 and dry["public_story_artifacts"] == 240, "materialization dry-run failed")
    require(all(dry[name] == 0 for name in ("writes_performed", "statistical_fits", "semantic_api_calls", "new_oracle_access", "validation_data_access", "holdout_data_access")), "dry-run boundary failure")
    require(dry["scene_ids_in_execution_order"] == json.loads((ROOT / cfg["parents"]["exact_plan"]["path"]).read_text(encoding="utf-8"))["exact_scene_ids_in_execution_order"], "identity order changed")
    require(dry["public_story_variants"] == ["full", "partial", "ambiguous"] and dry["study_semantic_variants_later"] == ["full", "partial"], "variant scope changed")
    require(cfg["scope"]["statistical_identity_count_later"] == 16480 and cfg["scope"]["semantic_logical_calls_later"] == 960, "future workload scope drift")
    require(all(value == 0 for value in cfg["boundaries"].values()), "checkpoint boundary changed")
    implementation = {"builder_sha256": digest(Path(__file__)), "runner_sha256": digest(RUNNER)}
    checkpoint = {"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_materialization_preflight.v1",
                  "task":cfg["task"],"status":"PASS_OFFLINE_PREFLIGHT","config_sha256":digest(CONFIG),
                  "parents":hashes,"implementation":implementation,"dry_plan":dry,
                  "materialized_scenes":0,"generated_public_stories":0,"statistical_fits":0,"semantic_api_calls":0,
                  "new_oracle_access":0,"validation_data_access":0,"holdout_data_access":0,
                  "live_materialization_authorized_by_this_preflight":False}
    body = canonical(checkpoint)
    audit = {"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_materialization_preflight_audit.v1",
             "status":"PASS_OFFLINE_PREFLIGHT","scene_count":80,"public_story_count":240,
             "checkpoint_sha256":sha_bytes(body),"config_sha256":digest(CONFIG),
             "runner_sha256":implementation["runner_sha256"],"exact_identity_sha256":hashes["exact_identities"]["sha256"],
             "study_writes":0,"statistical_fits":0,"semantic_api_calls":0,"new_oracle_access":0,
             "validation_data_access":0,"holdout_data_access":0}
    outputs(cfg,("preflight", "preflight_audit"),(body,canonical(audit)),check)
    return audit


def authorize(check: bool) -> dict[str, Any]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    preflight_audit = preflight(check=True)
    checkpoint_path = ROOT / cfg["outputs"]["preflight"]
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    require(checkpoint["status"] == "PASS_OFFLINE_PREFLIGHT" and preflight_audit["status"] == "PASS_OFFLINE_PREFLIGHT", "preflight not PASS")
    dry = dry_plan()
    require(dry == checkpoint["dry_plan"], "dry plan drift before authorization")
    auth = {"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_materialization_live_authorization.v1",
            "task":cfg["task"],"status":"PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION",
            "explicit_user_live_authorization":True,"preflight_sha256":digest(checkpoint_path),
            "preflight_audit_sha256":digest(ROOT / cfg["outputs"]["preflight_audit"]),
            "config_sha256":digest(CONFIG),"runner_sha256":digest(RUNNER),
            "exact_identities_sha256":cfg["parents"]["exact_identities"]["sha256"],
            "authorized_scene_ids":dry["scene_ids_in_execution_order"],"authorized_story_variants":["full","partial","ambiguous"],
            "materialization_authorized":True,"statistical_execution_authorized":False,"semantic_api_authorized":False,
            "oracle_scoring_authorized":False,"validation_authorized":False,"holdout_authorized":False,
            "automatic_execution_authorized":False}
    body=canonical(auth)
    audit={"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_materialization_live_authorization_audit.v1",
           "status":"PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION","preflight_pass":True,
           "authorized_scenes":80,"authorized_public_stories":240,"authorization_sha256":sha_bytes(body),
           "preflight_sha256":digest(checkpoint_path),"config_sha256":digest(CONFIG),"runner_sha256":digest(RUNNER),
           "materialization_executed":False,"statistical_fits":0,"semantic_api_calls":0,"new_oracle_access":0,
           "validation_data_access":0,"holdout_data_access":0}
    report=("# P1V4 Partial High supplemental 80: materialization preflight and authorization\n\n"
            "Offline preflight: **PASS**. Exactly 80 frozen P1V4SH identities and their component seeds, generator, T19 story rules, output paths and `cau` runtime were checked. The production materializer dry-run planned 80 observational scenes and 240 Full/Partial/Ambiguous public story artifacts with zero study writes. Only Full/Partial are registered for the later 960 semantic calls.\n\n"
            "Live authorization: **PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION** for exactly those 80 scenes and 240 public story artifacts. The authorization is a separate hash-pinned artifact. It does not start the runner and does not authorize statistical execution, provider preflight, semantic API, Oracle scoring, validation or holdout access.\n\n"
            "Next action: execute the scoped materializer with this authorization; verify materialization hashes and public-story leakage. Statistical execution requires its own checkpoint.\n").encode("utf-8")
    outputs(cfg,("authorization","authorization_audit","report"),(body,canonical(audit),report),check)
    return audit


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("preflight","authorize"))
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    result=preflight(args.check) if args.stage == "preflight" else authorize(args.check)
    print(json.dumps({"status":result["status"],"scenes":80,"public_stories":240,"study_writes":0,"api_calls":0,"replay":args.check}))


if __name__=="__main__":
    main()
