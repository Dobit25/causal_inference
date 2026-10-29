"""Materialize the exact frozen P1V4 validation look 160 without Oracle access."""
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
from run_p1_v4_independent_calibration_look120_materialization import construct_scene, write_or_verify

CONFIG = ROOT / "configs/p1_v4_validation_look160_materialization.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def load() -> tuple[dict, list[dict], dict, dict]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        require(path.is_file() and digest(path) == spec["sha256"], f"pinned parent drift: {name}")
    identities = [json.loads(line) for line in (ROOT / cfg["parents"]["exact_identities"]["path"]).read_text(encoding="utf-8").splitlines() if line]
    plan = json.loads((ROOT / cfg["parents"]["exact_plan"]["path"]).read_text(encoding="utf-8"))
    require(len(identities) == cfg["scope"]["scenes"] == 160, "scene count drift")
    require([x["study_id"] for x in identities] == plan["scene_ids_in_execution_order"], "identity order drift")
    require(len({x["study_id"] for x in identities}) == 160 and all(x["role"] == "threshold_validation" for x in identities), "identity role/uniqueness drift")
    require(all(x["first_registered_look"] == 160 and not x["scene_materialized"] for x in identities), "registered look drift")
    require(len(plan["ambiguous_scene_ids"]) == cfg["scope"]["ambiguous_subset_scenes"] == 120, "ambiguous subset drift")
    require(Path(sys.executable).resolve() == Path(cfg["runtime"]["canonical_python_executable"]).resolve(), "wrong Python environment")
    require(sys.version.split()[0] == cfg["runtime"]["python_version"] and np.__version__ == cfg["runtime"]["numpy_version"], "runtime version drift")
    generation = yaml.safe_load((ROOT / cfg["parents"]["generation_config"]["path"]).read_text(encoding="utf-8"))["generation"]
    story_cfg = yaml.safe_load((ROOT / cfg["parents"]["story_config"]["path"]).read_text(encoding="utf-8"))
    require(generation["observational_sample_size"] == cfg["scope"]["observations_per_scene"], "sample size drift")
    return cfg, identities, generation, story_cfg


def preflight() -> None:
    cfg, identities, _, _ = load()
    roots = [ROOT / cfg["scope"][key] for key in ("generated_root", "public_root")]
    populated = any(path.exists() and any(path.iterdir()) for path in roots)
    if populated:
        require((ROOT / cfg["scope"]["materialization_manifest"]).is_file(), "validation output root populated without prior scoped manifest")
    obj = {"status": "PASS_MATERIALIZATION_PREFLIGHT", "scene_ids": [x["study_id"] for x in identities], "scene_count": 160,
           "story_artifacts_planned": 480, "statistical_fits": 0, "semantic_api_calls": 0, "oracle_access": 0, "holdout_access": 0,
           "resume_existing_byte_equal_artifacts": populated, "config_sha256": digest(CONFIG), "runner_sha256": digest(Path(__file__))}
    out = ROOT / cfg["outputs"]["preflight"]
    out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(canonical(obj))
    auth = {"status": "PASS_SCOPED_MATERIALIZATION_AUTHORIZATION", "preflight_sha256": digest(out), "config_sha256": digest(CONFIG),
            "runner_sha256": digest(Path(__file__)), "authorized_scene_ids": obj["scene_ids"], "materialization": True,
            "statistical_execution": False, "semantic_api": False, "oracle": False, "holdout": False}
    (ROOT / cfg["outputs"]["authorization"]).write_bytes(canonical(auth))
    print(obj["status"], obj["scene_count"])


def execute() -> None:
    cfg, identities, generation, story_cfg = load()
    auth_path = ROOT / cfg["outputs"]["authorization"]
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    require(auth["status"] == "PASS_SCOPED_MATERIALIZATION_AUTHORIZATION" and auth["config_sha256"] == digest(CONFIG), "authorization invalid")
    require(auth["runner_sha256"] == digest(Path(__file__)) and auth["authorized_scene_ids"] == [x["study_id"] for x in identities], "authorization scope drift")
    require(auth["materialization"] and not any(auth[k] for k in ("statistical_execution", "semantic_api", "oracle", "holdout")), "authorization widened")
    gen_root, pub_root = ROOT / cfg["scope"]["generated_root"], ROOT / cfg["scope"]["public_root"]
    scenes, public, writes = [], [], 0
    ambiguous_ids = set(json.loads((ROOT / cfg["parents"]["exact_plan"]["path"]).read_text(encoding="utf-8"))["ambiguous_scene_ids"])
    for identity in identities:
        contents, metadata, records = construct_scene(identity, generation, story_cfg)
        require({r["variant"] for r in records} == {"full", "partial", "ambiguous"}, "story variants incomplete")
        dgen, dpub = gen_root / identity["study_id"], pub_root / identity["study_id"]
        for name in ("observations.npy", "metadata.json", "alias_map.json"):
            writes += int(write_or_verify(dgen / name, contents[name]))
        for record in records:
            path = dpub / f"story_{record['variant']}.json"
            writes += int(write_or_verify(path, contents[f"story_{record['variant']}.json"]))
            record["artifact_path"] = path.relative_to(ROOT).as_posix(); record["artifact_sha256"] = digest(path)
            record["leakage_check"] = {"oracle": False, "hidden_canonical_identifiers": False, "holdout": False, "gold_labels": False}
            record["semantic_scheduled"] = record["variant"] in {"full", "partial"} or (record["variant"] == "ambiguous" and identity["study_id"] in ambiguous_ids)
            public.append(record)
        scenes.append({"study_id": identity["study_id"], "scene_id": identity["contract_scene_id"],
                       "observation_path": (dgen / "observations.npy").relative_to(ROOT).as_posix(), "observation_sha256": digest(dgen / "observations.npy"),
                       "metadata_path": (dgen / "metadata.json").relative_to(ROOT).as_posix(), "metadata_sha256": digest(dgen / "metadata.json")})
    manifest = {"schema_version": "fourgraph.p1_v4_validation_look160_materialization.v1", "status": "PASS_MATERIALIZED",
                "scene_count": len(scenes), "records": scenes, "writes": writes, "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0}
    public_manifest = {"schema_version": "fourgraph.p1_v4_validation_look160_public_inputs.v1", "status": "PASS_PUBLIC_INPUTS",
                       "scene_count": len(scenes), "records": public, "full_partial_records": 320, "ambiguous_records": 160,
                       "ambiguous_semantic_subset_records": 120, "oracle_leakage": False, "holdout_leakage": False}
    mat_path, pub_path = ROOT / cfg["scope"]["materialization_manifest"], ROOT / cfg["scope"]["public_input_manifest"]
    mat_path.parent.mkdir(parents=True, exist_ok=True); mat_path.write_bytes(canonical(manifest)); pub_path.write_bytes(canonical(public_manifest))
    audit = {"status": "PASS_MATERIALIZATION_AUDIT", "scene_count": len(scenes), "public_records": len(public),
             "materialization_sha256": digest(mat_path), "public_inputs_sha256": digest(pub_path), "oracle_access": 0, "holdout_access": 0, "semantic_api_calls": 0}
    (ROOT / cfg["outputs"]["audit"]).write_bytes(canonical(audit))
    report = f"# P1V4 validation look 160 materialization\n\nPASS: {len(scenes)}/160 scenes and {len(public)}/480 public Full/Partial/Ambiguous story artifacts. No API, Oracle or holdout access.\n"
    (ROOT / cfg["outputs"]["report"]).write_text(report, encoding="utf-8")
    print(audit["status"], audit["scene_count"], audit["public_records"])


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("preflight", "execute")); args = parser.parse_args()
    (preflight if args.mode == "preflight" else execute)()


if __name__ == "__main__":
    main()
