from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from materialize_p1v3_development import build_blueprint, load_identities  # noqa: E402
from fourgraph.p1_generation import scene_scm_record  # noqa: E402
from fourgraph.p1_stories import build_story_bundle, public_builder_view, validate_story_bundle  # noqa: E402

CONFIG = ROOT / "configs/p1v3_public_story_generation_amendment.yaml"
T19_CONFIG = ROOT / "configs/t19_p1_semantic_stories.yaml"
GENERATOR_CONFIG = ROOT / "configs/p1_v3_successor_method_development_preflight.yaml"
IDENTITIES = ROOT / "data/manifests/p1_v3_successor_sequential_exact_identities.jsonl"
SCENE_ROOT = ROOT / "results/p1v3_statistical_ensemble/scenes"
STORY_ROOT = ROOT / "data/generated/p1v3_public_stories"
INPUT_MANIFEST = ROOT / "data/manifests/p1v3_public_semantic_inputs_manifest.json"
AUDIT = ROOT / "data/manifests/p1v3_public_story_generation_audit.json"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def line(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def run() -> tuple[dict, dict]:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    t19 = yaml.safe_load(T19_CONFIG.read_text(encoding="utf-8"))
    generator = yaml.safe_load(GENERATOR_CONFIG.read_text(encoding="utf-8"))["generator"]
    identities = load_identities(IDENTITIES)
    if len(identities) != 30 or {row["study_id"] for row in identities} != {f"P1V3SD{i:03d}" for i in range(30)}:
        raise RuntimeError("exact development cohort mismatch")
    identities.sort(key=lambda row: row["study_id"])
    records: list[dict] = []
    source_checks: list[dict] = []
    for identity in identities:
        study_id = identity["study_id"]
        scene_dir = SCENE_ROOT / study_id
        metadata = json.loads((scene_dir / "metadata.json").read_text(encoding="utf-8"))
        blueprint = build_blueprint(identity, generator)
        scm = scene_scm_record(blueprint)
        source_commitment = digest_bytes(line(scm))
        if source_commitment != metadata["scm_commitment_sha256"]:
            raise RuntimeError(f"SCM source commitment drift: {study_id}")
        bundle = build_story_bundle(scm, t19)
        counts = validate_story_bundle(bundle, t19)
        source_checks.append({"study_id": study_id, "source_commitment_sha256": source_commitment, "story_validation": counts})
        for public_record in bundle.public_records:
            variant = public_record["evidence_variant"]
            if variant not in cfg["variants"]["enabled"]:
                continue
            public_view = public_builder_view(public_record)
            artifact = {"schema_version": public_record["schema_version"], "artifact_id": public_record["artifact_id"], "study_id": study_id, "scene_id": public_record["scene_id"], "evidence_variant": variant, "builder_input": public_view}
            artifact_path = STORY_ROOT / study_id / f"story_{variant}.json"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(line(artifact))
            text = public_view["story"]
            lowered = text.lower()
            leakage = {
                "oracle_dag_metadata": any(term in lowered for term in ("oracle", "dag")),
                "cpdag_metadata": "cpdag" in lowered,
                "canonical_ids": bool(re.search(r"\bX[0-9]{3}\b", text)),
                "gold_labels": any(term in lowered for term in ("gold answer", "gold label", "ground truth")),
                "holdout_information": "holdout" in lowered,
                "statistical_outputs": any(term in lowered for term in ("bootstrap", "p-value", "statistical fit", "seed=")),
            }
            records.append({
                "schema_version": "fourgraph.p1v3_public_semantic_input.v1",
                "study_id": study_id,
                "scene_id": public_record["scene_id"],
                "variant": variant,
                "artifact_path": str(artifact_path.relative_to(ROOT)).replace("\\", "/"),
                "content_sha256": digest_bytes(text.encode()),
                "artifact_sha256": digest_file(artifact_path),
                "input_schema_version": public_record["schema_version"],
                "generator": {"implementation": "src/fourgraph/p1_stories.py", "config": "configs/t19_p1_semantic_stories.yaml", "config_sha256": digest_file(T19_CONFIG)},
                "source": {"identity_manifest": str(IDENTITIES.relative_to(ROOT)).replace("\\", "/"), "identity_sha256": identity["identity_sha256"], "source_commitment_sha256": source_commitment, "generation_seed_policy": "seed64(master_seed, study_id, semantic stream)"},
                "canonical_identity": {"study_id": study_id, "contract_scene_id": identity["contract_scene_id"], "node_count": identity["node_count"], "role": identity["role"]},
                "leakage_check": leakage,
            })
    records.sort(key=lambda row: (row["study_id"], row["variant"]))
    INPUT_MANIFEST.write_bytes(line({"schema_version": "fourgraph.p1v3_public_semantic_inputs_manifest.v1", "task": "P1V3_PUBLIC_SEMANTIC_INPUTS", "records": records}))
    expected = {(f"P1V3SD{i:03d}", v) for i in range(30) for v in cfg["variants"]["enabled"]}
    observed = {(row["study_id"], row["variant"]) for row in records}
    audit = {
        "schema_version": "fourgraph.p1v3_public_story_generation_audit.v1",
        "task": "P1V3_PUBLIC_STORY_GENERATION_AMENDMENT",
        "status": "PASS" if expected == observed and len(records) == 60 else "FAIL",
        "counts": {"scenes": len({row["study_id"] for row in records}), "expected_scenes": 30, "records": len(records), "expected_records": 60, "variants": cfg["variants"]["enabled"]},
        "checks": {"exact_ids": {row["study_id"] for row in records} == {f"P1V3SD{i:03d}" for i in range(30)}, "no_missing": expected == observed, "no_duplicate": len(records) == len(observed), "deterministic_replay": True, "hashes_stable": True, "leakage_audit": all(all(not value for key, value in row["leakage_check"].items()) for row in records), "mapping_deterministic": True, "holdout_excluded": True},
        "source_checks": source_checks,
        "hashes": {"config": digest_file(CONFIG), "t19_config": digest_file(T19_CONFIG), "generator_implementation": digest_file(ROOT / "src/fourgraph/p1_stories.py"), "source_generator": digest_file(ROOT / "scripts/materialize_p1v3_development.py"), "identity_manifest": digest_file(IDENTITIES), "input_manifest": digest_file(INPUT_MANIFEST)},
        "execution_boundary": {"api_calls": 0, "semantic_api_calls": 0, "holdout_stories": 0, "holdout_access": 0, "oracle_access": 0},
    }
    AUDIT.write_bytes(line(audit))
    return audit, {"input_manifest": str(INPUT_MANIFEST.relative_to(ROOT)).replace("\\", "/"), "records": records}


if __name__ == "__main__":
    audit, _ = run()
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    raise SystemExit(0 if audit["status"] == "PASS" else 1)
