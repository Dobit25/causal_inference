"""Dry-run-first materializer for the frozen 40-scene P1V4 look-160 increment."""

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
sys.path.insert(0, str(ROOT / "src"))

from run_p1_v4_independent_calibration_look120_materialization import construct_scene  # noqa: E402


CONFIG = ROOT / "configs/p1_v4_look160_incremental_materialization_preflight_authorization_checkpoint.yaml"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def load_scope() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        if not path.is_file() or sha(path) != spec["sha256"]:
            raise RuntimeError(f"pinned parent drift: {name}")
    rows = [
        json.loads(line)
        for line in (ROOT / cfg["parents"]["incremental_identities"]["path"]).read_text(encoding="utf-8").splitlines()
        if line
    ]
    plan = json.loads((ROOT / cfg["parents"]["incremental_plan"]["path"]).read_text(encoding="utf-8"))
    expected = plan["incremental_scene_ids_in_execution_order"]
    by_id = {row["study_id"]: row for row in rows}
    selected = [by_id[scene_id] for scene_id in expected]
    if len(selected) != cfg["scope"]["exact_incremental_scenes"] or len(set(expected)) != len(expected):
        raise RuntimeError("incremental identity scope drift")
    if any(row["batch_id"] != "semantic_calibration:120-160" for row in selected):
        raise RuntimeError("incremental batch drift")
    return cfg, selected


def dry_plan() -> dict[str, Any]:
    cfg, identities = load_scope()
    generation_contract = yaml.safe_load(
        (ROOT / cfg["parents"]["generation_contract"]["path"]).read_text(encoding="utf-8")
    )["generation"]
    for key in ("family", "observational_sample_size", "node_count_range", "edge_count_range", "minimum_oracle_cpdag_unresolved_edges"):
        if generation_contract[key] != cfg["generation"][key]:
            raise RuntimeError(f"generation contract drift: {key}")
    roots = [ROOT / cfg["scope"]["generated_scene_root"], ROOT / cfg["scope"]["public_story_root"]]
    if any(root.exists() and any(root.iterdir()) for root in roots):
        raise RuntimeError("reserved incremental output root is not empty")
    return {
        "status": "DRY_RUN_PASS",
        "scene_ids": [row["study_id"] for row in identities],
        "scene_count": len(identities),
        "story_variants": cfg["scope"]["story_variants"],
        "story_artifact_count": len(identities) * len(cfg["scope"]["story_variants"]),
        "component_seed_sha256": hashlib.sha256(
            canonical([row["component_seeds"] for row in identities])
        ).hexdigest().upper(),
        "generation": generation_contract,
        "writes_performed": 0,
        "semantic_api_calls": 0,
    }


def write_or_verify(path: Path, content: bytes) -> bool:
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"existing artifact differs: {path.relative_to(ROOT)}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        temporary.unlink()
    temporary.write_bytes(content)
    temporary.replace(path)
    return True


def execute(authorization_path: Path) -> dict[str, Any]:
    cfg, identities = load_scope()
    authorization_path = authorization_path.resolve()
    authorization = json.loads(authorization_path.read_text(encoding="utf-8"))
    if authorization.get("status") != "PASS_SCOPED_LOOK160_INCREMENTAL_MATERIALIZATION_AUTHORIZATION":
        raise RuntimeError("valid separate live materialization authorization required")
    auth = authorization.get("authorization", {})
    if auth.get("exact_scene_ids") != [row["study_id"] for row in identities]:
        raise RuntimeError("authorization scene scope drift")
    if auth.get("materialization_authorized") is not True or any(
        auth.get(key) is True
        for key in ("statistical_execution_authorized", "semantic_api_authorized", "oracle_access_authorized", "holdout_access_authorized")
    ):
        raise RuntimeError("authorization scope invalid")
    generation = yaml.safe_load((ROOT / cfg["parents"]["generation_contract"]["path"]).read_text(encoding="utf-8"))["generation"]
    story_config = yaml.safe_load((ROOT / cfg["parents"]["story_protocol"]["path"]).read_text(encoding="utf-8"))
    scene_root = ROOT / cfg["scope"]["generated_scene_root"]
    story_root = ROOT / cfg["scope"]["public_story_root"]
    scene_records: list[dict[str, Any]] = []
    story_records: list[dict[str, Any]] = []
    writes = 0
    for identity in identities:
        contents, metadata, records = construct_scene(identity, generation, story_config)
        scene_dir = scene_root / identity["study_id"]
        public_dir = story_root / identity["study_id"]
        for name in ("observations.npy", "metadata.json", "alias_map.json"):
            writes += int(write_or_verify(scene_dir / name, contents[name]))
        for record in records:
            path = public_dir / f"story_{record['variant']}.json"
            writes += int(write_or_verify(path, contents[f"story_{record['variant']}.json"]))
            record["artifact_path"] = path.relative_to(ROOT).as_posix()
        scene_records.append({
            "study_id": identity["study_id"],
            "scene_id": identity["contract_scene_id"],
            "observation_path": (scene_dir / "observations.npy").relative_to(ROOT).as_posix(),
            "metadata_path": (scene_dir / "metadata.json").relative_to(ROOT).as_posix(),
            "alias_map_path": (scene_dir / "alias_map.json").relative_to(ROOT).as_posix(),
            "observation_sha256": metadata["observation_sha256"],
            "scm_commitment_sha256": metadata["scm_commitment_sha256"],
        })
        story_records.extend(records)
    scene_manifest = {"schema_version": "fourgraph.p1_v4_calibration_look160_incremental_materialization.v1", "records": scene_records}
    public_manifest = {"schema_version": "fourgraph.p1_v4_calibration_look160_incremental_public_inputs.v1", "records": story_records}
    write_or_verify(ROOT / cfg["scope"]["materialization_manifest"], canonical(scene_manifest))
    write_or_verify(ROOT / cfg["scope"]["public_input_manifest"], canonical(public_manifest))
    return {"status": "PASS", "scenes": len(scene_records), "stories": len(story_records), "writes": writes}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if args.dry_run == args.execute:
        raise SystemExit("choose exactly one of --dry-run or --execute")
    if args.execute and args.authorization is None:
        raise SystemExit("--execute requires a separate --authorization artifact")
    result = dry_plan() if args.dry_run else execute(args.authorization)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
