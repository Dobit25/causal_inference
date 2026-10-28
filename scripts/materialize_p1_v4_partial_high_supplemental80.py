"""Scoped P1V4 supplemental materializer. --dry-run performs no study work."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from materialize_p1_v4_stage3 import seed64
from run_p1_v4_independent_calibration_look120_materialization import construct_scene, write_or_verify

CONFIG = ROOT / "configs/p1_v4_partial_high_supplemental80_materialization_preflight.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise RuntimeError(reason)


def load_scope(*, require_empty: bool) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        require(path.is_file() and digest(path) == spec["sha256"], f"pinned parent drift: {name}")
    protocol = json.loads((ROOT / cfg["parents"]["protocol"]["path"]).read_text(encoding="utf-8"))
    plan = json.loads((ROOT / cfg["parents"]["exact_plan"]["path"]).read_text(encoding="utf-8"))
    freeze = json.loads((ROOT / cfg["parents"]["freeze_audit"]["path"]).read_text(encoding="utf-8"))
    require(protocol["status"] == "PASS_FROZEN_OFFLINE_DESIGN" and freeze["status"] == "PASS_OFFLINE_FREEZE", "protocol freeze failed")
    require(all(freeze["identity_checks"].values()), "identity audit failed")
    rows = [json.loads(line) for line in (ROOT / cfg["parents"]["exact_identities"]["path"]).read_text(encoding="utf-8").splitlines() if line]
    ids = [row["study_id"] for row in rows]
    require(ids == plan["exact_scene_ids_in_execution_order"] and len(ids) == cfg["scope"]["scene_count"] == 80 and len(set(ids)) == 80, "80-scene order or identity drift")
    require(set(ids) == {f"P1V4SH{i:03d}" for i in range(80)}, "scene namespace drift")
    require(hashlib.sha256(b"".join(canonical(row) for row in rows)).hexdigest().upper() == plan["identities_sha256"], "identity bytes drift")
    for row in rows:
        require(row["role"] == "supplemental_high_confirmation" and row["first_registered_look"] == 80 and row["included_in_registered_looks"] == [80], "wrong study role/look")
        require(row["scene_materialized"] is False, "identity materialization flag changed")
        for component, value in row["component_seeds"].items():
            require(seed64(int(row["master_seed"]), row["study_id"], component) == value, f"seed drift: {row['study_id']}/{component}")
        payload = {key:value for key,value in row.items() if key != "identity_sha256"}
        require(hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest().upper() == row["identity_sha256"], "per-row identity hash drift")
    generation = yaml.safe_load((ROOT / cfg["parents"]["generation_config"]["path"]).read_text(encoding="utf-8"))["generation"]
    story = yaml.safe_load((ROOT / cfg["parents"]["story_config"]["path"]).read_text(encoding="utf-8"))
    require(generation["family"] == "linear_non_gaussian_acyclic" and generation["observational_sample_size"] == cfg["scope"]["observational_rows_per_scene"] == 2000, "generation parameters drift")
    require(story["stories"]["variants"] == cfg["scope"]["story_artifact_variants"] == ["full", "partial", "ambiguous"], "story variant contract drift")
    require(cfg["scope"]["public_story_artifact_count"] == 80 * 3 and cfg["scope"]["semantic_study_variants_later"] == ["full", "partial"], "story counts drift")
    require(cfg["scope"]["new_ambiguous_semantic_calls"] == 0, "ambiguous study calls unexpectedly added")
    require(Path(sys.executable).resolve() == Path(cfg["runtime"]["canonical_python_executable"]).resolve() and sys.version.split()[0] == cfg["runtime"]["python_version"] and np.__version__ == cfg["runtime"]["numpy_version"], "not canonical cau runtime")
    if require_empty:
        for key in ("generated_root", "public_root"):
            path = ROOT / cfg["scope"][key]
            require(not path.exists() or not any(path.iterdir()), f"reserved output root already populated: {key}")
        for key in ("materialization_manifest", "public_input_manifest"):
            require(not (ROOT / cfg["scope"][key]).exists(), f"unexpected existing output: {key}")
    return cfg, rows, generation


def dry_plan() -> dict[str, Any]:
    cfg, identities, _ = load_scope(require_empty=True)
    return {"status":"DRY_RUN_PASS","scene_count":len(identities),"scene_ids_in_execution_order":[row["study_id"] for row in identities],
            "public_story_variants":cfg["scope"]["story_artifact_variants"],"public_story_artifacts":240,
            "study_semantic_variants_later":cfg["scope"]["semantic_study_variants_later"],
            "component_seeds_sha256":hashlib.sha256(canonical([row["component_seeds"] for row in identities])).hexdigest().upper(),
            "generated_root":cfg["scope"]["generated_root"],"public_root":cfg["scope"]["public_root"],
            "writes_performed":0,"statistical_fits":0,"semantic_api_calls":0,"new_oracle_access":0,
            "validation_data_access":0,"holdout_data_access":0}


def execute(authorization_path: Path) -> dict[str, Any]:
    cfg, identities, generation = load_scope(require_empty=False)
    expected = (ROOT / cfg["outputs"]["authorization"]).resolve()
    require(authorization_path.resolve() == expected and expected.is_file(), "exact scoped authorization required")
    auth = json.loads(expected.read_text(encoding="utf-8"))
    preflight_path = ROOT / cfg["outputs"]["preflight"]
    require(preflight_path.is_file() and auth["preflight_sha256"] == digest(preflight_path), "preflight hash drift")
    require(auth["status"] == "PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION" and auth["authorized_scene_ids"] == [row["study_id"] for row in identities], "authorization scope drift")
    require(auth["config_sha256"] == digest(CONFIG) and auth["runner_sha256"] == digest(Path(__file__)), "execution config/runner drift")
    require(auth["materialization_authorized"] is True and all(auth[key] is False for key in ("statistical_execution_authorized", "semantic_api_authorized", "oracle_scoring_authorized", "validation_authorized", "holdout_authorized")), "authorization widened")
    story_cfg = yaml.safe_load((ROOT / cfg["parents"]["story_config"]["path"]).read_text(encoding="utf-8"))
    scenes, public, writes = [], [], 0
    scene_root = ROOT / cfg["scope"]["generated_root"]
    story_root = ROOT / cfg["scope"]["public_root"]
    for identity in identities:
        contents, metadata, records = construct_scene(identity, generation, story_cfg)
        require({r["variant"] for r in records} == {"full", "partial", "ambiguous"}, "missing public variant")
        d_scene, d_public = scene_root / identity["study_id"], story_root / identity["study_id"]
        for name in ("observations.npy", "metadata.json", "alias_map.json"):
            writes += int(write_or_verify(d_scene / name, contents[name]))
        for record in records:
            name = f"story_{record['variant']}.json"
            path = d_public / name
            writes += int(write_or_verify(path, contents[name]))
            record["artifact_path"] = path.relative_to(ROOT).as_posix()
        scenes.append({"study_id":identity["study_id"],"scene_id":identity["contract_scene_id"],
                       "observation_path":(d_scene / "observations.npy").relative_to(ROOT).as_posix(),
                       "metadata_path":(d_scene / "metadata.json").relative_to(ROOT).as_posix(),
                       "alias_map_path":(d_scene / "alias_map.json").relative_to(ROOT).as_posix(),
                       "observation_sha256":metadata["observation_sha256"],"scm_commitment_sha256":metadata["scm_commitment_sha256"]})
        public.extend(records)
    manifest_path=ROOT / cfg["scope"]["materialization_manifest"]
    public_path=ROOT / cfg["scope"]["public_input_manifest"]
    write_or_verify(manifest_path,canonical({"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_materialization.v1","records":scenes}))
    write_or_verify(public_path,canonical({"schema_version":"fourgraph.p1_v4_partial_high_supplemental80_public_inputs.v1","records":public}))
    require(len(scenes)==80 and len(public)==240 and all(not any(r["leakage_check"].values()) for r in public), "output completeness/leakage failure")
    require(not list(scene_root.rglob("story_truth.json")) and not list(story_root.rglob("story_truth.json")), "truth artifact leaked")
    audit={"status":"PASS_MATERIALIZED","scene_count":80,"public_story_count":240,"new_file_writes":writes,
           "manifest_sha256":digest(manifest_path),"public_input_sha256":digest(public_path),
           "statistical_fits":0,"semantic_api_calls":0,"new_oracle_access":0,"validation_data_access":0,"holdout_data_access":0}
    write_or_verify(ROOT / cfg["outputs"]["execution_audit"],canonical(audit))
    write_or_verify(ROOT / cfg["outputs"]["execution_report"],b"# P1V4 supplemental 80 materialization\n\nPASS: 80 scenes and 240 public stories. Statistical and semantic execution require separate authorization.\n")
    return audit


def main() -> None:
    ap=argparse.ArgumentParser()
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run",action="store_true")
    group.add_argument("--execute",action="store_true")
    ap.add_argument("--authorization",type=Path)
    args=ap.parse_args()
    if args.execute and args.authorization is None:
        raise SystemExit("--execute requires --authorization")
    result=dry_plan() if args.dry_run else execute(args.authorization)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    main()
