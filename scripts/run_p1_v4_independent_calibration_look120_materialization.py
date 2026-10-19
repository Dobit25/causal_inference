"""Materialize only the explicitly authorized P1V4 calibration look 120."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from materialize_p1_v4_stage3 import build_blueprint  # noqa: E402
from fourgraph.p1_generation import npy_bytes, sample_observations, scene_scm_record  # noqa: E402
from fourgraph.p1_stories import build_story_bundle, public_builder_view, validate_story_bundle  # noqa: E402

CONFIG = ROOT / "configs/p1_v4_independent_calibration_look120_materialization_execution.yaml"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def write_or_verify(path: Path, content: bytes) -> bool:
    """Write atomically once, or require exact bytes when resuming."""
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


def load() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    for name, spec in cfg["parents"].items():
        path = ROOT / spec["path"]
        if not path.is_file() or sha(path) != spec["sha256"]:
            raise RuntimeError(f"pinned parent drift: {name}")
    auth = json.loads((ROOT / cfg["parents"]["live_authorization"]["path"]).read_text(encoding="utf-8"))
    if auth["status"] != "PASS_SCOPED_LIVE_MATERIALIZATION_AUTHORIZATION":
        raise RuntimeError("live materialization is not authorized")
    if auth["authorization"]["statistical_execution_authorized"] or auth["authorization"]["semantic_api_calls_authorized"]:
        raise RuntimeError("authorization scope unexpectedly widened")
    preflight = json.loads((ROOT / cfg["parents"]["materialization_preflight"]["path"]).read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (ROOT / cfg["parents"]["exact_identities"]["path"]).read_text(encoding="utf-8").splitlines() if line]
    by_id = {row["study_id"]: row for row in rows}
    identities = [by_id[study_id] for study_id in preflight["exact_scene_ids_in_execution_order"]]
    if len(identities) != 120 or any(row["role"] != "semantic_calibration" for row in identities):
        raise RuntimeError("look-120 identity scope drift")
    generation_config = yaml.safe_load((ROOT / cfg["generation_source"]["config"]).read_text(encoding="utf-8"))
    if sha(ROOT / cfg["generation_source"]["config"]) != cfg["generation_source"]["sha256"]:
        raise RuntimeError("generation config hash drift")
    return cfg, generation_config["generation"], identities


def leakage_flags(story: str) -> dict[str, bool]:
    lowered = story.lower()
    return {
        "canonical_ids": bool(re.search(r"\bX[0-9]{3}\b", story)),
        "oracle_or_graph_metadata": any(term in lowered for term in ("oracle", "cpdag", "dag", "ground truth", "seed=")),
        "holdout_information": "holdout" in lowered,
        "statistical_metadata": any(term in lowered for term in ("bootstrap", "p-value", "statistical fit")),
    }


def construct_scene(identity: dict[str, Any], generation: dict[str, Any], story_config: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any], list[dict[str, Any]]]:
    blueprint = build_blueprint(identity, generation)
    observations = sample_observations(blueprint, int(identity["master_seed"]), int(generation["observational_sample_size"]))
    observation_bytes = npy_bytes(observations)
    scm_commitment = sha_bytes(canonical(scene_scm_record(blueprint)))
    metadata = {
        "schema_version": "fourgraph.p1_v4_calibration_execution_scene.v1",
        "study_id": identity["study_id"], "scene_id": identity["contract_scene_id"],
        "nodes": list(blueprint.dag.nodes), "observation_rows": int(observations.shape[0]),
        "observation_sha256": sha_bytes(observation_bytes), "scm_commitment_sha256": scm_commitment,
        "component_seeds": dict(blueprint.component_seeds),
    }
    bundle = build_story_bundle(scene_scm_record(blueprint), story_config)
    validation = validate_story_bundle(bundle, story_config)
    records: list[dict[str, Any]] = []
    contents: dict[str, bytes] = {"observations.npy": observation_bytes, "metadata.json": canonical(metadata), "alias_map.json": canonical({"schema_version": "fourgraph.p1_v4_alias_mapping.v1", "study_id": identity["study_id"], "alias_map": dict(bundle.alias_map)})}
    for record in bundle.public_records:
        public = public_builder_view(record)
        variant = record["evidence_variant"]
        artifact = {"schema_version": record["schema_version"], "builder_input": public}
        story_bytes = canonical(artifact)
        flags = leakage_flags(public["story"])
        if any(flags.values()):
            raise RuntimeError(f"public-story leakage: {identity['study_id']}/{variant}")
        contents[f"story_{variant}.json"] = story_bytes
        records.append({
            "schema_version": "fourgraph.p1_v4_calibration_public_input.v1",
            "study_id": identity["study_id"], "scene_id": identity["contract_scene_id"], "variant": variant,
            "content_sha256": sha_bytes(public["story"].encode("utf-8")), "artifact_sha256": sha_bytes(story_bytes),
            "story_validation": validation[variant], "leakage_check": flags,
            "source_commitment_sha256": scm_commitment,
        })
    return contents, metadata, records


def run(execute: bool) -> dict[str, Any]:
    cfg, generation, identities = load()
    if not execute:
        return {"status": "DRY_RUN_PASS", "scenes": len(identities), "stories": len(identities) * 3, "writes": 0}
    story_config = yaml.safe_load((ROOT / cfg["parents"]["story_protocol"]["path"]).read_text(encoding="utf-8"))
    scene_root = ROOT / cfg["runtime"]["scene_root"]
    story_root = ROOT / cfg["runtime"]["public_story_root"]
    scene_records: list[dict[str, Any]] = []
    story_records: list[dict[str, Any]] = []
    writes = 0
    for identity in identities:
        contents, metadata, records = construct_scene(identity, generation, story_config)
        scene_dir = scene_root / identity["study_id"]
        story_dir = story_root / identity["study_id"]
        writes += int(write_or_verify(scene_dir / "observations.npy", contents["observations.npy"]))
        writes += int(write_or_verify(scene_dir / "metadata.json", contents["metadata.json"]))
        writes += int(write_or_verify(scene_dir / "alias_map.json", contents["alias_map.json"]))
        for record in records:
            variant = record["variant"]
            path = story_dir / f"story_{variant}.json"
            writes += int(write_or_verify(path, contents[f"story_{variant}.json"]))
            record["artifact_path"] = path.relative_to(ROOT).as_posix()
        scene_records.append({"study_id": identity["study_id"], "scene_id": identity["contract_scene_id"], "observation_path": (scene_dir / "observations.npy").relative_to(ROOT).as_posix(), "metadata_path": (scene_dir / "metadata.json").relative_to(ROOT).as_posix(), "alias_map_path": (scene_dir / "alias_map.json").relative_to(ROOT).as_posix(), "observation_sha256": metadata["observation_sha256"], "scm_commitment_sha256": metadata["scm_commitment_sha256"]})
        story_records.extend(records)
    scene_manifest = {"schema_version": "fourgraph.p1_v4_calibration_look120_materialization_manifest.v1", "task": cfg["task"], "records": scene_records}
    public_manifest = {"schema_version": "fourgraph.p1_v4_calibration_look120_public_input_manifest.v1", "task": cfg["task"], "records": story_records}
    write_or_verify(ROOT / cfg["outputs"]["materialization_manifest"], canonical(scene_manifest))
    write_or_verify(ROOT / cfg["outputs"]["public_input_manifest"], canonical(public_manifest))
    required_scene = [record["study_id"] for record in scene_records]
    forbidden_truth_paths = list(scene_root.rglob("story_truth.json")) + list(story_root.rglob("story_truth.json"))
    persisted_text = b"".join(path.read_bytes() for path in list(scene_root.rglob("*.json")) + list(story_root.rglob("*.json")))
    audit = {"schema_version": "fourgraph.p1_v4_calibration_look120_materialization_execution_audit.v1", "task": cfg["task"], "status": "PASS", "counts": {"scenes": len(scene_records), "observations": len(scene_records), "scene_artifacts": len(scene_records) * 3, "public_stories": len(story_records)}, "checks": {"exact_120_execution_order": required_scene == [identity["study_id"] for identity in identities], "all_story_variants_present": {(record["study_id"], record["variant"]) for record in story_records} == {(identity["study_id"], variant) for identity in identities for variant in ("full", "partial", "ambiguous")}, "no_public_story_leakage": all(not any(record["leakage_check"].values()) for record in story_records), "no_oracle_truth_persisted": not forbidden_truth_paths and b'"oracle_dag"' not in persisted_text and b'"oracle_cpdag"' not in persisted_text, "statistical_fits_zero": cfg["boundary"]["statistical_fits"] == 0, "semantic_api_calls_zero": cfg["boundary"]["semantic_api_calls"] == 0, "oracle_scoring_access_zero": cfg["boundary"]["oracle_scoring_access"] is False, "holdout_access_zero": cfg["boundary"]["holdout_access"] is False}, "hashes": {"materialization_manifest": sha(ROOT / cfg["outputs"]["materialization_manifest"]), "public_input_manifest": sha(ROOT / cfg["outputs"]["public_input_manifest"]), "config": sha(CONFIG), "execution_runner": sha(Path(__file__))}, "boundary": cfg["boundary"], "next_action": "STATISTICAL_PARENT_PREFLIGHT_OR_AUTHORIZATION_REQUIRED"}
    if not all(audit["checks"].values()):
        audit["status"] = "FAIL"
    write_or_verify(ROOT / cfg["outputs"]["audit"], canonical(audit))
    report = f"# P1V4 calibration look-120 materialization\n\nStatus: **{audit['status']}**. Materialized exactly {len(scene_records)} authorized linear non-Gaussian observational scenes and {len(story_records)} public Full/Partial/Ambiguous stories. No statistical fit, semantic API call, Oracle scoring, holdout access, or downstream analysis occurred.\n".encode()
    write_or_verify(ROOT / cfg["outputs"]["report"], report)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--execute", action="store_true"); args = parser.parse_args()
    if args.dry_run == args.execute: raise SystemExit("choose exactly one of --dry-run or --execute")
    result = run(args.execute)
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] not in ("PASS", "DRY_RUN_PASS"): raise SystemExit("materialization failed")
    return 0

if __name__ == "__main__": raise SystemExit(main())
